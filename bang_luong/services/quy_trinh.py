"""Kiểm tra căn cứ, lưu thiết lập và xử lý duyệt/chi trả lương."""
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import transaction
from nhan_vien.access import yeu_cau_vai_tro, NHAN_SU, GIAM_DOC
from bang_luong.models import Luong
from bang_cong.thang_lich import thang_lich, thang_tu_ma
from .tinh_toan import du_lieu_tinh_luong
from .thue import loi_nguon_thue
from thuong.services.tinh_toan import cac_khoan_thuong_tinh_luong


def loi_nguon_thuong(record):
    attendance = thang_lich(record.tong_hop.nam, record.tong_hop.thang)
    try:
        rows = cac_khoan_thuong_tinh_luong(record.tong_hop.nhan_vien_id, attendance.nam, attendance.thang)
    except ValidationError as error:
        return '; '.join(error.messages)
    total = sum((Decimal(row['amount']) for row in rows), Decimal(0))
    return '' if total == record.tong_tien_thuong else 'Bonuses changed; recalculate payroll before approval or payment.'


def loi_nguon_tang_ca(record):
    attendance = thang_lich(record.tong_hop.nam, record.tong_hop.thang)
    try:
        values = du_lieu_tinh_luong(record.tong_hop.nhan_vien, attendance, attendance)
    except ValidationError as error:
        return '; '.join(error.messages)
    return '' if Decimal(str(values['luong_tang_ca'])) == Decimal(str(record.luong_tang_ca)) else (
        'Overtime changed; recalculate payroll before approval or payment.')


def loi_duyet_luong(record, period=None, attendance=None):
    period = period or thang_lich(record.tong_hop.nam, record.tong_hop.thang)
    attendance = attendance or period
    approved = attendance.employee_approvals.filter(
        tong_hop__nhan_vien_id=record.tong_hop.nhan_vien_id).exists()
    if not approved and attendance.trang_thai != 'approved':
        return 'Attendance for this employee has not been approved.'
    try:
        values = du_lieu_tinh_luong(record.tong_hop.nhan_vien, attendance, period)
    except ValidationError as error:
        return '; '.join(error.messages)
    fields = ('luong_co_ban', 'luong_theo_cong', 'luong_tang_ca', 'tong_tien_thuong',
              'khau_tru_di_tre', 'khau_tru_bhxh', 'thue_tncn', 'luong_thuc_linh')
    for field in fields:
        precision = Luong._meta.get_field(field).decimal_places
        expected = Decimal(str(values[field])).quantize(Decimal(1).scaleb(-precision))
        if Decimal(str(getattr(record, field))) != expected:
            return 'Payroll sources changed; recalculate before approval.'
    return ''

@transaction.atomic
def gui_bang_luong(actor, period_id):
    """HR submits the complete, attendance-approved month for director approval."""
    yeu_cau_vai_tro(actor, NHAN_SU)
    attendance = thang_tu_ma(period_id)
    records = list(attendance.records.select_for_update().select_related(
        'tong_hop', 'tong_hop__nhan_vien',
    ).order_by('pk'))
    if attendance.trang_thai != 'approved':
        raise ValidationError('Cần duyệt toàn bộ bảng công trước khi gửi bảng lương.')
    if not records:
        raise ValidationError('Kỳ này chưa có phiếu lương để gửi duyệt.')
    approved_employee_ids = set(attendance.ds_nhan_vien)
    payroll_employee_ids = {record.tong_hop.nhan_vien_id for record in records}
    if payroll_employee_ids != approved_employee_ids:
        raise ValidationError('Cần tính đủ phiếu lương cho toàn bộ nhân viên đã duyệt công.')
    if any(record.trang_thai != 'pending' for record in records):
        raise ValidationError('Chỉ gửi được kỳ lương đang chờ HR kiểm tra.')
    for record in records:
        loi = loi_duyet_luong(record, attendance, attendance) or loi_nguon_thuong(record)
        if loi:
            raise ValidationError(f'{record.ma_nhan_vien}: {loi}')
    attendance.records.filter(trang_thai='pending').update(trang_thai='submitted')


@transaction.atomic
def xu_ly_trang_thai_luong(actor, period_id, action, reason, evidence=''):
    if action == 'approve':
        yeu_cau_vai_tro(actor, GIAM_DOC)
    elif action == 'paid':
        yeu_cau_vai_tro(actor, GIAM_DOC)
    elif action == 'reopen':
        yeu_cau_vai_tro(actor, NHAN_SU, GIAM_DOC)
    else:
        raise ValidationError('Thao tác không hợp lệ.')
    if not reason.strip():
        raise ValidationError('Cần ghi lý do.')
    period = thang_tu_ma(period_id)
    attendance = period
    list(period.records.select_for_update().order_by('pk'))
    if action == 'approve':
        if period.status != 'submitted' or not period.records.exists():
            raise ValidationError('HR cần gửi toàn bộ kỳ lương để Giám đốc ký duyệt.')
        if attendance.trang_thai != 'approved':
            raise ValidationError('Bảng công chưa được duyệt.')
        if period.records.exclude(trang_thai='submitted').exists():
            raise ValidationError('Tất cả phiếu lương trong kỳ phải được HR gửi duyệt.')
        for record in period.records.filter(trang_thai='submitted'):
            loi = loi_duyet_luong(record, period, attendance)
            if loi:
                raise ValidationError(f'{record.ma_nhan_vien}: {loi}')
        period.records.filter(trang_thai='submitted').update(trang_thai='approved')
    elif action == 'paid':
        from .hien_thi import phieu_luong_du_cong_duyet
        if period.records.exclude(pk__in=phieu_luong_du_cong_duyet(period.records.all()).values('pk')).exists():
            raise ValidationError('Bảng công chưa duyệt, không được chi trả lương.')
        if period.status != 'approved' or not evidence.strip():
            raise ValidationError('Chỉ xác nhận kỳ đã duyệt khi có bằng chứng thanh toán.')
        for record in period.records.all():
            loi = loi_nguon_thuong(record) or loi_nguon_tang_ca(record) or loi_nguon_thue(record)
            if loi:
                raise ValidationError(f'{record.ma_nhan_vien}: {loi}')
        period.records.all().update(trang_thai='paid')
    elif action == 'reopen':
        if period.status not in ['submitted', 'approved']:
            raise ValidationError('Chỉ mở lại kỳ đã gửi hoặc đã duyệt và chưa chi trả.')
        period.records.all().update(trang_thai='pending')
    else:
        raise ValidationError('Thao tác không hợp lệ.')
    if action == 'reopen':
        from .tinh_toan import cap_nhat_luong_nhan_vien
        for employee_id in period.records.filter(trang_thai='pending').values_list('tong_hop__nhan_vien_id', flat=True):
            cap_nhat_luong_nhan_vien(actor, employee_id, attendance.nam, attendance.thang)


class CanCuLuong(SimpleNamespace):
    """Căn cứ trong bộ nhớ, không phải model hay bảng dữ liệu theo kỳ."""

    def full_clean(self):
        if not self.verified or not self.tax_basis or not self.insurance_basis:
            raise ValidationError('Thiếu thiết lập bảo hiểm/thuế đã được NHAN_SU xác nhận.')
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
    settings = employee.thiet_lap_luong
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
    gia_tri.tax_dependents = getattr(employee, '_snapshot_tax_dependents', settings.get('tax_dependents', 0))
    gia_tri.shared_settings = settings
    gia_tri.full_clean()
    return gia_tri


def cac_khoan_phu_cap_khau_tru(employee, period):
    if hasattr(employee, '_snapshot_adjustments'):
        return employee._snapshot_adjustments
    from bang_luong.models import Luong
    existing = Luong.objects.filter(tong_hop__nhan_vien=employee,
                                    tong_hop__nam=period.nam, tong_hop__thang=period.thang).first()
    historical = cac_khoan_da_luu(existing) if existing else []
    historical = [dong for dong in historical if dong.tax_category != 'meal_cash'
                  and dong.name not in ['Phụ cấp ăn trưa', 'Ăn trưa']]
    settings = employee.thiet_lap_luong or {}
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
    employee.thiet_lap_luong=record.chi_tiet.get('source_data',{}).get('employee_settings')
    if employee.thiet_lap_luong is None:
        chi_tiet = record.chi_tiet
        tax = chi_tiet.get('source_data', {}).get('tax_inputs', {})
        employee.thiet_lap_luong = {
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
    yeu_cau_vai_tro(actor,NHAN_SU,GIAM_DOC)
    from nhan_vien.models import NhanVien
    from django.utils import timezone
    employee=NhanVien.objects.select_for_update().get(pk=employee.pk)
    from nhan_vien.forms import BieuMauThietLapLuong
    # Dữ liệu lưu dùng khóa nội bộ tiếng Anh; form nhận tên trường tiếng Việt.
    payload = {
        f'salary-{ten_truong}': settings[khoa]
        for ten_truong, khoa in BieuMauThietLapLuong.KHOA_CAU_HINH.items()
        if khoa in settings
    }
    for ten_truong, ma_bao_hiem in BieuMauThietLapLuong.KHOA_TY_LE.items():
        payload[f'salary-{ten_truong}'] = Decimal(str(
            settings.get('insurance_rates', {}).get(ma_bao_hiem, 0))) * 100
    bieu_mau=BieuMauThietLapLuong(employee,data=payload)
    if not bieu_mau.is_valid():
        raise ValidationError(bieu_mau.errors.as_text())
    settings=bieu_mau.du_lieu_thiet_lap()
    du_lieu_cu=employee.thiet_lap_luong
    employee.payroll_errors=[]
    comparable={khoa:gia_tri for khoa,gia_tri in (du_lieu_cu or {}).items() if not khoa.startswith('_')}
    if comparable==settings:
        return employee
    employee.thiet_lap_luong={**settings,'_updated_by':actor.pk,'_updated_at':timezone.now().isoformat()}
    employee.save(update_fields=['thiet_lap_luong'])
    from .tinh_toan import cap_nhat_luong_nhan_vien
    months = Luong.objects.filter(trang_thai='pending').values_list(
        'tong_hop__nam', 'tong_hop__thang',
    ).distinct().order_by('tong_hop__nam', 'tong_hop__thang')
    for year, month in months:
        loi=cap_nhat_luong_nhan_vien(actor,employee.pk,year,month)
        if loi: employee.payroll_errors.append(loi)
    return employee
