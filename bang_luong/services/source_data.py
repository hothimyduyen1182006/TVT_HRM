"""Bản chụp dữ liệu tính lương; bỏ qua thời gian, người duyệt và ghi chú."""

from django.db.models import F
from datetime import date, time
from decimal import Decimal
from bang_cong.models import LichLamViec
from nghi_phep.models import LeaveDay


def canonical(value):
    if isinstance(value, Decimal):
        return format(value.normalize(), 'f')
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical(item) for item in value]
    return value


def source_data(employee, attendance, inputs, records, overtime, bonuses, adjustments, tax_details):
    adjustment_rows = ([{'id':row.pk,'kind':row.kind,'amount':row.amount,'tax_category':row.tax_category}
                        for row in adjustments] if isinstance(adjustments,list) else
                        list(adjustments.order_by('pk').values('id','kind','amount','tax_category')))
    data = {
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
        'overtime': [{key: row[key] for key in ['id','date','start','end','hours','multiplier']} for row in overtime],
        'overtime_policy': 'automatic-checkout-1700-v1',
        'overtime_hourly_rate': inputs.overtime_hourly_rate,
        'overtime_basis':inputs.overtime_basis,
        'bonuses': list(bonuses.order_by('pk').values('id', 'amount')),
        'adjustments': [{key:row[key] for key in ['id','kind','amount']} for row in adjustment_rows],
        'insurance_base': inputs.insurance_base,
        'insurance_rates': {key: Decimal(str(rate)) for key, rate in inputs.insurance_rates.items()},
        'tax': tax_details['tax'],
    }
    if inputs.tax_method != 'legacy':
        data['tax_calculation'] = tax_details
        data['tax_inputs'] = {'method': inputs.tax_method, 'dependents': inputs.tax_dependents,
            'personal_deduction': inputs.claim_personal_deduction, 'exempt_ot': inputs.tax_exempt_overtime}
        data['adjustments'] = adjustment_rows
    if employee.payroll_settings is not None:
        data['employee_settings'] = employee.payroll_settings
    return canonical(data)


def legacy_breakdown(breakdown):
    """Đối chiếu các thành phần đã lưu cho phiếu cũ chưa có source_data."""
    return {
        'insurance_base': Decimal(str(breakdown['insurance_base'])),
        'insurance_rates': {key: Decimal(str(value)) for key, value in breakdown['insurance_rates'].items()},
        'insurance': {key: Decimal(str(value)) for key, value in breakdown['insurance'].items()},
        'hourly_rate': Decimal(str(breakdown['hourly_rate'])),
        'ot': sorted((item['date'], Decimal(item['hours']), Decimal(item['multiplier']), Decimal(item['amount']))
                     for item in breakdown.get('ot', [])),
        'bonuses': sorted((item['id'], Decimal(item['amount'])) for item in breakdown.get('bonuses', [])),
        'adjustments': sorted((item['id'], item['kind'], Decimal(item['amount']))
                              for item in breakdown.get('adjustments', [])),
    }
