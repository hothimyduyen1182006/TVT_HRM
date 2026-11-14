"""Tính lương, liên kết nguồn và chuẩn hóa dữ liệu đối chiếu."""
from datetime import date, time
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum
from nhan_vien.access import require_role, HR, DIRECTOR
from nhan_vien.models import Employee
from bang_cong.models import KyCong, ChamCong, LichLamViec
from thuong.models import Bonus, payroll_bonus_records
from nghi_phep.models import LeaveDay
from bang_luong.models import PayrollPeriod, Luong, PayrollAuditLog
from .thue import tinh_thue_tncn


ZERO = Decimal(0)


SIMULATED_LATE_HOURLY_RATE = Decimal('100000')


def tong_gia_tri(queryset, field):
    return queryset.aggregate(value=Sum(field))['value'] or ZERO


def chup_du_lieu_luong(period):
    return [{k: str(v) for k, v in dong.items()} for dong in period.records.values()]


def lien_ket_nguon_luong(record):
    """Ghi liên kết nguồn cùng giao dịch lưu phiếu, không dùng trong GET."""
    from uuid import uuid4
    from bang_cong.models import TongHopCong
    from thuong.models import TongThuong

    attendance = record.ky_luong.attendance_period
    if not record.ma_luong:
        code = f'L{attendance.nam}{attendance.thang:02}-{record.nhan_vien_id}'
        record.ma_luong = code if len(code) <= 20 else 'L' + uuid4().hex[:19]
    if not record.tong_hop_id:
        record.tong_hop, _ = TongHopCong.objects.get_or_create(
            ky_cong=attendance, nhan_vien_id=record.nhan_vien_id,
            defaults={'thang': attendance.thang, 'nam': attendance.nam,
                      'cong_chuan': record.cong_chuan, 'tong_cong': record.cong_huong_luong,
                      'cong_nghi_co_luong': record.cong_nghi_phep,
                      'gio_tang_ca': record.so_gio_tang_ca, 'so_phut_tre': record.so_phut_tre},
        )
    if (record.tong_hop.ky_cong_id, record.tong_hop.nhan_vien_id) != (attendance.pk, record.nhan_vien_id):
        raise ValidationError('Tổng hợp công phải thuộc đúng nhân viên và kỳ lương.')
    defaults = {'tong_tien': record.tong_tien_thuong,
                'chi_tiet': record.chi_tiet.get('bonuses', [])}
    if record.trang_thai == 'pending':
        record.tong_thuong, _ = TongThuong.objects.update_or_create(
            nhan_vien_id=record.nhan_vien_id, nam=attendance.nam, thang=attendance.thang,
            defaults=defaults,
        )
    elif not record.tong_thuong_id:
        record.tong_thuong, _ = TongThuong.objects.get_or_create(
            nhan_vien_id=record.nhan_vien_id, nam=attendance.nam, thang=attendance.thang,
            defaults=defaults,
        )
    if (record.tong_thuong.nhan_vien_id, record.tong_thuong.nam, record.tong_thuong.thang) != (
            record.nhan_vien_id, attendance.nam, attendance.thang):
        raise ValidationError('Tổng thưởng phải thuộc đúng nhân viên và kỳ lương.')


def phieu_luong_can_tinh_lai(period, attendance=None):
    """Phiếu chờ duyệt sẽ bị thay thế trong lần tính này."""
    attendance = attendance or period.attendance_period
    employee_ids = (attendance.ds_nhan_vien if attendance.trang_thai == 'approved'
                    else attendance.employee_approvals.values_list('nhan_vien_id', flat=True))
    return period.records.filter(trang_thai='pending', nhan_vien_id__in=employee_ids)


@transaction.atomic
def tinh_bang_luong(actor, period_id, reason):
    require_role(actor, HR, DIRECTOR)
    # Cùng thứ tự khóa với workflow công: kỳ công trước, kỳ lương sau.
    link = PayrollPeriod.objects.get(pk=period_id)
    attendance = KyCong.objects.select_for_update().get(pk=link.attendance_period_id)
    period = PayrollPeriod.objects.select_for_update().get(pk=period_id)
    if period.status != 'pending':
        raise ValidationError('Không tính lại lương đã duyệt/chi trả.')
    approved_ids = list(attendance.employee_approvals.values_list('nhan_vien_id', flat=True))
    if attendance.trang_thai != 'approved' and not approved_ids:
        raise ValidationError('Chưa có nhân viên được duyệt bảng công trong kỳ.')
    standard = tong_gia_tri(LichLamViec.objects.filter(ngay__year=attendance.nam, ngay__month=attendance.thang), 'cong_chuan')
    if standard <= 0 or attendance.gio_chuan <= 0:
        raise ValidationError('Công chuẩn phải lớn hơn 0.')
    employee_ids = attendance.ds_nhan_vien if attendance.trang_thai == 'approved' else approved_ids
    employees = Employee.objects.filter(pk__in=employee_ids)
    if not employees.exists():
        raise ValidationError('Không có nhân viên trong kỳ.')
    replacing = phieu_luong_can_tinh_lai(period, attendance)
    reason = reason.strip()
    if replacing.exists() and not reason:
        raise ValidationError('Cần ghi lý do tính lại lương.')
    reason = reason or f'Tạo phiếu lương mới kỳ {attendance.thang:02}/{attendance.nam}'
    PayrollAuditLog.objects.create(period=period, actor=actor, action='before_calculate', reason=reason, snapshot=chup_du_lieu_luong(period))
    # Cập nhật tại chỗ để giữ ID và các khoản lịch sử trong snapshot của phiếu.
    for employee in employees.select_related('department'):
        if period.records.filter(nhan_vien=employee, trang_thai__in=['approved', 'paid']).exists():
            continue  # Giữ nguyên phiếu đã duyệt khi tính lại phần còn chờ duyệt.
        from bang_cong.services.quy_trinh import cap_nhat_tong_hop
        cap_nhat_tong_hop(employee, attendance)
        Luong.objects.update_or_create(
            ky_luong=period, nhan_vien=employee,
            defaults=du_lieu_tinh_luong(employee, attendance, period, standard),
        )
    period.attendance_revision = attendance.phien_ban
    period.save()
    PayrollAuditLog.objects.create(period=period, actor=actor, action='calculate', reason=reason, snapshot=chup_du_lieu_luong(period))
    return period


@transaction.atomic
def cap_nhat_luong_nhan_vien(actor, employee_id, year, month):
    """Cập nhật đúng một nhân viên/kỳ sau thao tác lưu nguồn đã được phân quyền."""
    from .quy_trinh import loi_duyet_luong
    require_role(actor, HR, DIRECTOR)
    attendance = KyCong.objects.select_for_update().filter(nam=year, thang=month).first()
    if not attendance:
        return ''
    approved = (employee_id in attendance.ds_nhan_vien if attendance.trang_thai == 'approved' else
                attendance.employee_approvals.filter(nhan_vien_id=employee_id).exists())
    if not approved:
        return ''  # Chờ duyệt công, không tự duyệt hoặc dùng công chưa xác nhận.
    period, _ = PayrollPeriod.objects.get_or_create(attendance_period=attendance)
    period = PayrollPeriod.objects.select_for_update().get(pk=period.pk)
    if period.status != 'pending':
        return ''
    dong = period.records.select_for_update().filter(nhan_vien_id=employee_id).first()
    if dong and dong.trang_thai != 'pending':
        return ''
    employee = Employee.objects.select_related('department').get(pk=employee_id)
    from bang_cong.services.quy_trinh import cap_nhat_tong_hop
    cap_nhat_tong_hop(employee, attendance)
    same_identity = dong and (dong.ma_nhan_vien, dong.ten_nhan_vien, dong.ma_phong_ban_luu, dong.ten_phong_ban) == (
        employee.code, employee.full_name, employee.department_id, employee.department.name)
    if same_identity and not loi_duyet_luong(dong, period, attendance):
        return ''
    try:
        cac_gia_tri = du_lieu_tinh_luong(employee, attendance, period)
    except ValidationError as loi:
        return f'{employee.code}: ' + '; '.join(loi.messages)
    du_lieu_cu = [{k: str(v) for k, v in phan_tu.items()} for phan_tu in period.records.filter(nhan_vien_id=employee_id).values()]
    dong, _ = Luong.objects.update_or_create(ky_luong=period, nhan_vien=employee, defaults=cac_gia_tri)
    period.attendance_revision = attendance.phien_ban
    period.save(update_fields=['attendance_revision'])
    du_lieu_moi = [{k: str(v) for k, v in phan_tu.items()} for phan_tu in period.records.filter(pk=dong.pk).values()]
    PayrollAuditLog.objects.create(period=period, actor=actor, action='auto_calculate',
        reason=f'Tự cập nhật lương {employee.code} sau thay đổi dữ liệu nguồn',
        snapshot=[{'before': du_lieu_cu, 'after': du_lieu_moi}])
    return ''


def du_lieu_tinh_luong(employee, attendance, period, standard=None):
    """Tính trong bộ nhớ để tạo hoặc đối chiếu phiếu; không ghi dữ liệu."""
    if standard is None:
        standard = tong_gia_tri(LichLamViec.objects.filter(ngay__year=attendance.nam, ngay__month=attendance.thang), 'cong_chuan')
    if standard <= 0 or attendance.gio_chuan <= 0:
        raise ValidationError('Công chuẩn phải lớn hơn 0.')
    from .quy_trinh import can_cu_luong_nhan_vien,cac_khoan_phu_cap_khau_tru
    inputs = can_cu_luong_nhan_vien(employee,period)
    inputs.full_clean()
    records = ChamCong.objects.filter(nhan_vien=employee, ngay__year=attendance.nam, ngay__month=attendance.thang)
    from bang_cong.services.quy_trinh import tong_hop_dung_tinh_luong
    summary = tong_hop_dung_tinh_luong(employee, attendance)
    cong_huong_luong = summary.tong_cong
    hourly = employee.base_salary / standard / attendance.gio_chuan
    luong_theo_cong = employee.base_salary / standard * cong_huong_luong
    from bang_cong.services.tinh_toan import tong_hop_tang_ca_tinh_luong
    overtime=tong_hop_tang_ca_tinh_luong(employee,attendance.nam,attendance.thang)
    if overtime and (not inputs.overtime_hourly_rate or not inputs.overtime_basis.strip()):
        raise ValidationError(f'{employee}: HR cần nhập lương giờ căn cứ OT và căn cứ áp dụng trước khi tính lương.')
    ot_rate=inputs.overtime_hourly_rate or ZERO
    ot_lines=[{**{khoa: str(dong[khoa]) if khoa in ['hours','multiplier'] else dong[khoa]
                     for khoa in ['id','date','start','end','hours','multiplier']},
               'amount': str(ot_rate * dong['hours'] * dong['multiplier'])} for dong in overtime]
    ot_pay=sum((Decimal(phan_tu['amount']) for phan_tu in ot_lines),ZERO)
    bonuses = payroll_bonus_records(Bonus.objects.filter(
        employee=employee, year=attendance.nam, month=attendance.thang))
    bonus_lines = [{'id': dong.pk, 'name': dong.name, 'amount': str(dong.amount)} for dong in bonuses]
    thuong = sum((Decimal(line['amount']) for line in bonus_lines), ZERO)
    adjustments = cac_khoan_phu_cap_khau_tru(employee,period)
    allowance = sum((dong.amount for dong in adjustments if dong.kind=='allowance'),ZERO)
    late_minutes = tong_gia_tri(records, 'so_phut_tre')
    # Quy tắc mô phỏng đồ án, tách riêng với phần lương giảm do thiếu công.
    late_penalty = (SIMULATED_LATE_HOURLY_RATE * late_minutes / Decimal(60)).quantize(
        Decimal('1'), rounding=ROUND_HALF_UP,
    )
    deductions = sum((dong.amount for dong in adjustments if dong.kind=='deduction'),ZERO) + late_penalty
    chi_tiet_bao_hiem = {ten: str(inputs.insurance_base * Decimal(str(ty_le)))
                       for ten, ty_le in inputs.insurance_rates.items()}
    bao_hiem = sum((Decimal(value) for value in chi_tiet_bao_hiem.values()), ZERO)
    tax_details = tinh_thue_tncn(inputs, attendance, luong_theo_cong, ot_pay, thuong, bao_hiem, adjustments, overtime)
    tax = tax_details['tax']
    net = luong_theo_cong + ot_pay + thuong + allowance - bao_hiem - tax - deductions
    cac_gia_tri = dict(
        ky_luong=period, nhan_vien=employee, ma_nhan_vien=employee.code, ten_nhan_vien=employee.full_name,
        ma_phong_ban_luu=employee.department_id, ten_phong_ban=employee.department.name,
        luong_co_ban=employee.base_salary, cong_chuan=standard, cong_huong_luong=cong_huong_luong,
        cong_nghi_phep=tong_gia_tri(LeaveDay.objects.filter(employee=employee, date__year=attendance.nam,
                                                 date__month=attendance.thang, approved=True), 'units'),
        so_phut_tre=late_minutes, so_gio_tang_ca=sum((dong['hours'] for dong in overtime),ZERO), luong_theo_cong=luong_theo_cong,
        luong_tang_ca=ot_pay, tong_tien_thuong=thuong, phu_cap=allowance, tong_bao_hiem=bao_hiem, thue_tncn=tax,
        tong_khau_tru=deductions, luong_thuc_linh=net.quantize(Decimal('1'), rounding=ROUND_HALF_UP),
        chi_tiet={'attendance_revision': attendance.phien_ban,
                   'late_penalty': {'amount': str(late_penalty), 'minutes': int(late_minutes),
                                    'hourly_rate': str(SIMULATED_LATE_HOURLY_RATE), 'simulation': True},
                   'ot': ot_lines, 'overtime_warnings': [warning for dong in overtime for warning in dong['warnings']], 'bonuses': bonus_lines, 'insurance': chi_tiet_bao_hiem,
                   'overtime_hourly_rate':str(ot_rate),'overtime_basis':inputs.overtime_basis,
                   'insurance_base': str(inputs.insurance_base), 'insurance_rates': inputs.insurance_rates,
                   'tax_basis': inputs.tax_basis, 'tax_calculation': chuan_hoa_du_lieu(tax_details), 'insurance_basis': inputs.insurance_basis,
                   'hourly_rate': str(hourly), 'attendance_pay_exact': str(luong_theo_cong), 'net_exact': str(net),
                   'adjustments': [{'id': dong.pk, 'name': dong.name, 'kind': dong.kind,
                                    'amount': str(dong.amount), 'basis': dong.basis} for dong in adjustments]})

    cac_gia_tri['chi_tiet']['source_data'] = du_lieu_nguon(employee, attendance, inputs, records, overtime, bonuses, adjustments, tax_details)
    cac_gia_tri.update(khau_tru_di_tre=late_penalty, khau_tru_khac=deductions-late_penalty,
                  khau_tru_bhxh=Decimal(chi_tiet_bao_hiem.get('BHXH', '0')),
                  khau_tru_bhyt=Decimal(chi_tiet_bao_hiem.get('BHYT', '0')),
                  khau_tru_bhtn=Decimal(chi_tiet_bao_hiem.get('BHTN', '0')))
    return cac_gia_tri


def chuan_hoa_du_lieu(value):
    if isinstance(value, Decimal):
        return format(value.normalize(), 'f')
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {khoa: chuan_hoa_du_lieu(phan_tu) for khoa, phan_tu in value.items()}
    if isinstance(value, (list, tuple)):
        return [chuan_hoa_du_lieu(phan_tu) for phan_tu in value]
    return value


def du_lieu_nguon(employee, attendance, inputs, records, overtime, bonuses, adjustments, tax_details):
    adjustment_rows = ([{'id':dong.pk,'kind':dong.kind,'amount':dong.amount,'tax_category':dong.tax_category}
                        for dong in adjustments] if isinstance(adjustments,list) else
                        list(adjustments.order_by('pk').values('id','kind','amount','tax_category')))
    du_lieu = {
        'base_salary': employee.base_salary,
        'schedule': [attendance.gio_bat_dau, attendance.bat_dau_nghi_trua, attendance.ket_thuc_nghi_trua,
                     attendance.gio_ket_thuc, attendance.gio_chuan],
        'calendar': list(LichLamViec.objects.filter(ngay__year=attendance.nam,
            ngay__month=attendance.thang).order_by('ngay').values(**{'date': F('ngay'), 'kind': F('loai_ngay'), 'expected_units': F('cong_chuan')})),
        'attendance': list(records.order_by('ngay').values(**{
            'date': F('ngay'), 'check_in': F('gio_vao'), 'check_out': F('gio_ra'),
            'status': F('trang_thai'), 'work_hours': F('so_gio_lam'),
            'late_minutes': F('so_phut_tre'), 'actual_units': F('cong_thuc_te'),
            'paid_leave_units': F('cong_nghi_co_luong'), 'paid_units': F('tong_cong'),
        })),
        'leave': list(LeaveDay.objects.filter(employee=employee, date__year=attendance.nam,
            date__month=attendance.thang, approved=True).order_by('date').values('date', 'units', 'paid')),
        'overtime': [{khoa: dong[khoa] for khoa in ['id','date','start','end','hours','multiplier']} for dong in overtime],
        'overtime_policy': 'automatic-checkout-1700-v1',
        'overtime_hourly_rate': inputs.overtime_hourly_rate,
        'overtime_basis':inputs.overtime_basis,
        'bonuses': list(bonuses.order_by('pk').values('id', 'amount')),
        'adjustments': [{khoa:dong[khoa] for khoa in ['id','kind','amount']} for dong in adjustment_rows],
        'insurance_base': inputs.insurance_base,
        'insurance_rates': {khoa: Decimal(str(ty_le)) for khoa, ty_le in inputs.insurance_rates.items()},
        'tax': tax_details['tax'],
    }
    if inputs.tax_method != 'legacy':
        du_lieu['tax_calculation'] = tax_details
        du_lieu['tax_inputs'] = {'method': inputs.tax_method, 'dependents': inputs.tax_dependents,
            'personal_deduction': inputs.claim_personal_deduction, 'exempt_ot': inputs.tax_exempt_overtime}
        du_lieu['adjustments'] = adjustment_rows
    if employee.payroll_settings is not None:
        du_lieu['employee_settings'] = employee.payroll_settings
    return chuan_hoa_du_lieu(du_lieu)


def doi_chieu_chi_tiet_cu(breakdown):
    """Đối chiếu các thành phần đã lưu cho phiếu cũ chưa có source_data."""
    return {
        'insurance_base': Decimal(str(breakdown['insurance_base'])),
        'insurance_rates': {khoa: Decimal(str(value)) for khoa, value in breakdown['insurance_rates'].items()},
        'insurance': {khoa: Decimal(str(value)) for khoa, value in breakdown['insurance'].items()},
        'hourly_rate': Decimal(str(breakdown['hourly_rate'])),
        'ot': sorted((phan_tu['date'], Decimal(phan_tu['hours']), Decimal(phan_tu['multiplier']), Decimal(phan_tu['amount']))
                     for phan_tu in breakdown.get('ot', [])),
        'bonuses': sorted((phan_tu['id'], Decimal(phan_tu['amount'])) for phan_tu in breakdown.get('bonuses', [])),
        'adjustments': sorted((phan_tu['id'], phan_tu['kind'], Decimal(phan_tu['amount']))
                              for phan_tu in breakdown.get('adjustments', [])),
    }
