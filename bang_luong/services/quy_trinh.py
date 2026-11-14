"""Kiểm tra căn cứ, lưu thiết lập và xử lý duyệt/chi trả lương."""
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone
from bang_cong.models import KyCong
from nhan_vien.access import require_role, HR, DIRECTOR
from bang_luong.models import PayrollPeriod, PayrollAuditLog, Luong
from .tinh_toan import chup_du_lieu_luong, du_lieu_tinh_luong, doi_chieu_chi_tiet_cu
from .thue import loi_nguon_thue
from thuong.models import Bonus, payroll_bonus_records


def loi_nguon_thuong(record):
    """Đối chiếu thưởng nguồn, không sửa phiếu lương đã khóa."""
    attendance = record.ky_luong.attendance_period
    try:
        ds_dong = payroll_bonus_records(Bonus.objects.filter(employee_id=record.nhan_vien_id,
            year=attendance.nam, month=attendance.thang))
        hien_tai = {dong.pk: dong.amount for dong in ds_dong}
        da_luu = {int(phan_tu['id']): Decimal(str(phan_tu['amount']))
                 for phan_tu in record.chi_tiet.get('bonuses', [])}
    except ValidationError as loi:
        return '; '.join(loi.messages)
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return 'Phiếu lương thiếu thông tin thưởng nguồn để đối chiếu. Cần kiểm tra lại trước khi chi trả.'
    if hien_tai != da_luu or sum(hien_tai.values(), Decimal(0)) != record.tong_tien_thuong:
        return 'Bảng thưởng đã thay đổi so với phiếu lương đã lưu. Cần mở lại và tính lại lương trước khi chi trả.'
    return ''


def loi_nguon_tang_ca(record):
    from bang_cong.services.tinh_toan import tong_hop_tang_ca_tinh_luong, CHINH_SACH_OT
    attendance = record.ky_luong.attendance_period
    try:
        ds_dong = tong_hop_tang_ca_tinh_luong(record.nhan_vien, attendance.nam, attendance.thang)
        if (ds_dong or record.so_gio_tang_ca or record.luong_tang_ca) and record.chi_tiet.get('source_data', {}).get('overtime_policy') != CHINH_SACH_OT:
            return 'Nguồn OT thuộc cơ chế cũ. Cần mở lại và tính lại lương; giữ nguyên phiếu đã chi trả.'
        hien_tai = {dong['id']: (dong['date'], dong['start'], dong['end'], dong['hours'], dong['multiplier']) for dong in ds_dong}
        da_luu = {int(phan_tu['id']): (phan_tu['date'], phan_tu['start'], phan_tu['end'], Decimal(phan_tu['hours']), Decimal(phan_tu['multiplier'])) for phan_tu in record.chi_tiet.get('ot', [])}
        ty_le = Decimal(str(record.chi_tiet.get('overtime_hourly_rate', 0)))
        if ds_dong:
            inputs = can_cu_luong_nhan_vien(nhan_vien_theo_phieu_luong(record),record.ky_luong)
            if (not inputs or not inputs.overtime_hourly_rate or not inputs.overtime_basis.strip()
                    or ty_le != inputs.overtime_hourly_rate
                    or record.chi_tiet.get('overtime_basis') != inputs.overtime_basis):
                return 'Căn cứ lương giờ OT đã thay đổi hoặc còn thiếu. Cần mở lại và tính lại lương.'
        expected_amount = sum((dong['hours'] * dong['multiplier'] * ty_le for dong in ds_dong), Decimal(0))
        saved_amount = sum((Decimal(phan_tu['amount']) for phan_tu in record.chi_tiet.get('ot', [])), Decimal(0))
        if hien_tai != da_luu or sum((dong['hours'] for dong in ds_dong), Decimal(0)) != record.so_gio_tang_ca or expected_amount.quantize(Decimal('0.00000001')) != record.luong_tang_ca or saved_amount != expected_amount:
            return 'Nguồn OT đã thay đổi. Cần mở lại và tính lại lương trước khi duyệt hoặc chi trả.'
    except ValidationError as loi:
        return '; '.join(loi.messages)
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return 'Thiếu nguồn OT để đối chiếu. Cần mở lại và tính lại lương.'
    return ''


def loi_duyet_luong(record, period=None, attendance=None):
    loi = loi_nguon_tang_ca(record)
    if loi:
        return loi
    period = period or record.ky_luong
    attendance = attendance or period.attendance_period
    approval = attendance.employee_approvals.filter(nhan_vien_id=record.nhan_vien_id).first()
    if not approval and attendance.trang_thai != 'approved':
        return 'Bảng công của nhân viên này chưa được duyệt.'
    try:
        hien_tai = du_lieu_tinh_luong(record.nhan_vien, attendance, period)
    except ValidationError as loi:
        return '; '.join(loi.messages)
    da_thay_doi = False
    for truong in ['luong_co_ban', 'cong_chuan', 'cong_huong_luong', 'cong_nghi_phep', 'so_phut_tre', 'so_gio_tang_ca',
                  'luong_theo_cong', 'luong_tang_ca', 'tong_tien_thuong', 'phu_cap', 'tong_bao_hiem', 'thue_tncn',
                  'tong_khau_tru', 'luong_thuc_linh', 'khau_tru_di_tre', 'khau_tru_bhxh',
                  'khau_tru_bhyt', 'khau_tru_bhtn', 'khau_tru_khac']:
        du_kien = hien_tai[truong]
        definition = Luong._meta.get_field(truong)
        if isinstance(du_kien, Decimal) and hasattr(definition, 'decimal_places'):
            du_kien = du_kien.quantize(Decimal(1).scaleb(-definition.decimal_places))
            if connection.vendor == 'sqlite':
                # Compare the same representation Django reads from SQLite's REAL storage.
                # The calculation and saved amounts are unchanged; avoid false stale-source errors.
                expression = definition.get_col(record._meta.db_table)
                prepared = definition.get_db_prep_save(du_kien, connection)
                converter = connection.ops.get_decimalfield_converter(expression)
                du_kien = converter(float(prepared), expression, connection)
        if getattr(record, truong) != du_kien:
            da_thay_doi = True
            break
    if not da_thay_doi:
        if 'source_data' in record.chi_tiet:
            da_thay_doi = record.chi_tiet['source_data'] != hien_tai['chi_tiet']['source_data']
        else:
            try:
                da_thay_doi = doi_chieu_chi_tiet_cu(record.chi_tiet) != doi_chieu_chi_tiet_cu(hien_tai['chi_tiet'])
            except (KeyError, TypeError, ValueError, InvalidOperation):
                return 'Phiếu cũ thiếu dữ liệu đối chiếu. Hãy tính lại lương trước khi duyệt.'
    if da_thay_doi:
        return 'Dữ liệu nguồn đã thay đổi và lương chưa cập nhật được. Cần kiểm tra căn cứ tính lương trước khi duyệt.'
    return ''


@transaction.atomic
def xu_ly_trang_thai_luong(actor, period_id, action, reason, evidence=''):
    require_role(actor, DIRECTOR)
    if not reason.strip():
        raise ValidationError('Cần ghi lý do.')
    link = PayrollPeriod.objects.get(pk=period_id)
    attendance = KyCong.objects.select_for_update().get(pk=link.attendance_period_id)
    period = PayrollPeriod.objects.select_for_update().get(pk=period_id)
    if action == 'approve':
        if period.status != 'pending' or not period.records.exists():
            raise ValidationError('Cần kỳ chờ duyệt có kết quả tính lương.')
        if attendance.trang_thai != 'approved':
            raise ValidationError('Bảng công chưa được duyệt.')
        for record in period.records.all():
            loi = loi_nguon_tang_ca(record) or loi_nguon_thue(record)
            if loi:
                raise ValidationError(f'{record.ma_nhan_vien}: {loi}')
        for record in period.records.filter(trang_thai='pending'):
            loi = loi_duyet_luong(record, period, attendance)
            if loi:
                raise ValidationError(f'{record.ma_nhan_vien}: {loi}')
        period.status = 'approved'
        period.approved_by = actor
        period.approved_at = timezone.now()
        period.records.filter(trang_thai='pending').update(trang_thai='approved', nguoi_duyet=actor, ngay_duyet=period.approved_at)
    elif action == 'paid':
        from .hien_thi import phieu_luong_du_cong_duyet
        if period.records.exclude(pk__in=phieu_luong_du_cong_duyet(period.records.all()).values('pk')).exists():
            raise ValidationError('Bảng công chưa duyệt, không được chi trả lương.')
        if period.status != 'approved' or not evidence.strip() or period.records.filter(trang_thai='pending').exists():
            raise ValidationError('Chỉ xác nhận kỳ đã duyệt khi có bằng chứng thanh toán.')
        for record in period.records.all():
            loi = loi_nguon_thuong(record) or loi_nguon_tang_ca(record) or loi_nguon_thue(record)
            if loi:
                raise ValidationError(f'{record.ma_nhan_vien}: {loi}')
        period.status = 'paid'
        period.paid_by = actor
        period.paid_at = timezone.now()
        period.payment_evidence = evidence
        period.records.all().update(trang_thai='paid')
    elif action == 'reopen':
        if period.status == 'paid' or not (period.status == 'approved' or period.records.filter(trang_thai='approved').exists()):
            raise ValidationError('Chỉ mở lại kỳ đã duyệt và chưa chi trả.')
        period.status = 'pending'
        period.approved_by = None
        period.approved_at = None
        period.attendance_revision = 0  # Bắt buộc tính lại trước khi duyệt.
        period.records.all().update(trang_thai='pending', nguoi_duyet=None, ngay_duyet=None)
    else:
        raise ValidationError('Thao tác không hợp lệ.')
    period.save()
    PayrollAuditLog.objects.create(period=period, actor=actor, action=action, reason=reason, snapshot=chup_du_lieu_luong(period))
    if action == 'reopen':
        from .tinh_toan import cap_nhat_luong_nhan_vien
        for employee_id in period.records.filter(trang_thai='pending').values_list('nhan_vien_id', flat=True):
            cap_nhat_luong_nhan_vien(actor, employee_id, attendance.nam, attendance.thang)


@transaction.atomic
def duyet_phieu_luong(actor, record_id):
    require_role(actor, DIRECTOR)
    link = Luong.objects.select_related('ky_luong').get(pk=record_id)
    attendance = KyCong.objects.select_for_update().get(pk=link.ky_luong.attendance_period_id)
    period = PayrollPeriod.objects.select_for_update().get(pk=link.ky_luong_id)
    record = Luong.objects.select_for_update().get(pk=record_id)
    if record.trang_thai != 'pending' or period.status != 'pending':
        raise ValidationError('Phiếu lương này đã duyệt hoặc đã chi trả.')
    loi = loi_duyet_luong(record, period, attendance)
    if loi:
        raise ValidationError(loi)
    record.trang_thai = 'approved'
    record.nguoi_duyet = actor
    record.ngay_duyet = timezone.now()
    record.save(update_fields=['trang_thai', 'nguoi_duyet', 'ngay_duyet'])
    expected_ids = set(attendance.ds_nhan_vien)
    approved_ids = set(period.records.filter(trang_thai__in=['approved', 'paid']).values_list('nhan_vien_id', flat=True))
    if (attendance.trang_thai == 'approved' and expected_ids and expected_ids.issubset(approved_ids)
            and not period.records.filter(trang_thai='pending').exists()):
        period.status = 'approved'
        period.approved_by = actor
        period.approved_at = record.ngay_duyet
        period.save()
    PayrollAuditLog.objects.create(period=period, actor=actor, action='approve_employee',
        reason=f'Duyệt phiếu lương riêng của {record.ma_nhan_vien}',
        snapshot=[{khoa: str(gia_tri) for khoa, gia_tri in Luong.objects.filter(pk=record.pk).values().get().items()}])
    return record


class CanCuLuong(SimpleNamespace):
    """Căn cứ trong bộ nhớ, không phải model hay bảng dữ liệu theo kỳ."""

    def full_clean(self):
        if not self.verified or not self.tax_basis or not self.insurance_basis:
            raise ValidationError('Thiếu thiết lập bảo hiểm/thuế đã được HR xác nhận.')
        if self.insurance_base is None or not self.insurance_base.is_finite() or self.insurance_base < 0:
            raise ValidationError('Lương đóng bảo hiểm phải là số không âm.')
        if not isinstance(self.insurance_rates, dict):
            raise ValidationError('Tỷ lệ bảo hiểm phải là danh sách theo mã bảo hiểm.')
        tong_gia_tri = Decimal(0)
        try:
            for ten, ty_le in self.insurance_rates.items():
                gia_tri = Decimal(str(ty_le))
                if not ten or not gia_tri.is_finite() or not 0 <= gia_tri <= 1:
                    raise ValueError
                tong_gia_tri += gia_tri
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError('Tỷ lệ bảo hiểm phải từ 0 đến 1.')
        if tong_gia_tri > 1:
            raise ValidationError('Tổng tỷ lệ bảo hiểm không được vượt 100%.')
        if self.overtime_hourly_rate is not None and (
                not self.overtime_hourly_rate.is_finite() or self.overtime_hourly_rate <= 0
                or not self.overtime_basis.strip()):
            raise ValidationError('Lương giờ OT phải lớn hơn 0 và có căn cứ áp dụng.')
        if self.tax_exempt_overtime is not None and (
                not self.tax_exempt_overtime.is_finite() or self.tax_exempt_overtime < 0):
            raise ValidationError('Tiền OT miễn thuế phải là số không âm.')


def can_cu_luong_nhan_vien(employee, period):
    """Chỉ đọc thiết lập chung của nhân viên hoặc snapshot khi đối chiếu phiếu cũ."""
    settings = employee.payroll_settings
    if not settings or not settings.get('verified'):
        raise ValidationError(f'{employee}: cần thiết lập và xác nhận tính lương trong Quản lý nhân viên.')
    defaults = dict(insurance_base=0, insurance_rates={}, insurance_basis='',
                    tax_method='resident_2026', tax_basis='', tax_amount=0,
                    claim_personal_deduction=True, overtime_hourly_rate=None,
                    overtime_basis='', verified=False, tax_exempt_overtime=None)
    gia_tri = CanCuLuong(**{khoa: settings.get(khoa, default) for khoa, default in defaults.items()})
    try:
        for khoa in ['insurance_base', 'overtime_hourly_rate', 'tax_exempt_overtime', 'tax_amount']:
            raw = getattr(gia_tri, khoa)
            if raw is not None:
                setattr(gia_tri, khoa, Decimal(str(raw)))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError('Thiết lập tiền bảo hiểm, thuế hoặc OT không hợp lệ.')
    gia_tri.tax_dependents = getattr(employee, '_snapshot_tax_dependents', 0)
    gia_tri.shared_settings = settings
    gia_tri.full_clean()
    return gia_tri


def cac_khoan_phu_cap_khau_tru(employee, period):
    if hasattr(employee, '_snapshot_adjustments'):
        return employee._snapshot_adjustments
    from bang_luong.models import Luong
    existing = Luong.objects.filter(nhan_vien=employee, ky_luong=period).first()
    historical = cac_khoan_da_luu(existing) if existing else []
    historical = [dong for dong in historical if dong.tax_category != 'meal_cash'
                  and dong.name not in ['Phụ cấp ăn trưa', 'Ăn trưa']]
    settings = employee.payroll_settings or {}
    return historical+[SimpleNamespace(pk=f'employee-{employee.pk}-lunch',name='Phụ cấp ăn trưa',kind='allowance',
        amount=Decimal(str(settings.get('lunch_allowance',450000))),tax_category='meal_cash',
        basis='Phụ cấp ăn trưa dùng chung đã được xác nhận trong quản lý nhân viên')]


def cac_khoan_da_luu(record):
    chi_tiet = record.chi_tiet
    categories = {str(phan_tu['id']): phan_tu.get('tax_category', 'taxable')
                  for phan_tu in chi_tiet.get('source_data', {}).get('adjustments', [])}
    return [SimpleNamespace(pk=phan_tu['id'], name=phan_tu['name'], kind=phan_tu['kind'],
                            amount=Decimal(str(phan_tu['amount'])), basis=phan_tu.get('basis', ''),
                            tax_category=categories.get(str(phan_tu['id']),
                                'meal_cash' if phan_tu['name'] in ['Phụ cấp ăn trưa', 'Ăn trưa'] else 'taxable'))
            for phan_tu in chi_tiet.get('adjustments', [])]


def nhan_vien_theo_phieu_luong(record):
    """Phiếu đã lưu dùng bản chụp thiết lập của chính nó để đối soát thuế/OT."""
    from copy import copy
    employee=copy(record.nhan_vien)
    employee.payroll_settings=record.chi_tiet.get('source_data',{}).get('employee_settings')
    if employee.payroll_settings is None:
        chi_tiet = record.chi_tiet
        tax = chi_tiet.get('source_data', {}).get('tax_inputs', {})
        employee.payroll_settings = {
            'insurance_base': chi_tiet.get('insurance_base', '0'),
            'insurance_rates': chi_tiet.get('insurance_rates', {}),
            'insurance_basis': chi_tiet.get('insurance_basis', ''),
            'tax_method': tax.get('method', 'legacy'), 'tax_amount': str(record.thue_tncn),
            'tax_basis': chi_tiet.get('tax_basis', ''),
            'claim_personal_deduction': tax.get('personal_deduction', True),
            'tax_exempt_overtime': tax.get('exempt_ot'),
            'overtime_hourly_rate': chi_tiet.get('overtime_hourly_rate'),
            'overtime_basis': chi_tiet.get('overtime_basis', ''), 'verified': True,
        }
        employee._snapshot_tax_dependents = tax.get('dependents', 0)
    employee._snapshot_adjustments = cac_khoan_da_luu(record)
    return employee


@transaction.atomic
def luu_thiet_lap_luong(actor, employee, settings):
    require_role(actor,HR,DIRECTOR)
    from nhan_vien.models import Employee
    from django.utils import timezone
    employee=Employee.objects.select_for_update().get(pk=employee.pk)
    from nhan_vien.forms import SalarySettingsForm
    payload={f'salary-{khoa}':gia_tri for khoa,gia_tri in settings.items()}
    for khoa in ['bhxh','bhyt','bhtn']:
        payload[f'salary-{khoa}']=Decimal(str(settings.get('insurance_rates',{}).get(khoa.upper(),0)))*100
    bieu_mau=SalarySettingsForm(employee,data=payload)
    if not bieu_mau.is_valid():
        raise ValidationError(bieu_mau.errors.as_text())
    settings=bieu_mau.settings_data()
    du_lieu_cu=employee.payroll_settings
    employee.payroll_errors=[]
    comparable={khoa:gia_tri for khoa,gia_tri in (du_lieu_cu or {}).items() if not khoa.startswith('_')}
    if comparable==settings:
        return employee
    employee.payroll_settings={**settings,'_updated_by':actor.pk,'_updated_at':timezone.now().isoformat()}
    employee.save(update_fields=['payroll_settings'])
    period=PayrollPeriod.objects.filter(records__nhan_vien=employee).order_by('-attendance_period__nam','-attendance_period__thang').first()
    if period:
        PayrollAuditLog.objects.create(period=period,actor=actor,action='employee_settings',
            reason=f'Cập nhật thiết lập tính lương dùng chung của {employee.code}',
            snapshot=[{'employee_id':employee.pk,'before':du_lieu_cu,'after':employee.payroll_settings}])
    from .tinh_toan import cap_nhat_luong_nhan_vien
    for period in PayrollPeriod.objects.filter(status='pending').select_related('attendance_period').order_by('attendance_period_id'):
        attendance=period.attendance_period
        loi=cap_nhat_luong_nhan_vien(actor,employee.pk,attendance.nam,attendance.thang)
        if loi: employee.payroll_errors.append(loi)
    return employee
