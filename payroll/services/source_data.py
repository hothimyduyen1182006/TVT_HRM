"""Bản chụp dữ liệu tính lương; bỏ qua thời gian, người duyệt và ghi chú."""
from datetime import date, time
from decimal import Decimal
from attendance.models import WorkCalendarDay
from leaves.models import LeaveDay


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


def source_data(employee, attendance, inputs, records, overtime, bonuses, adjustments):
    return canonical({
        'base_salary': employee.base_salary,
        'schedule': [attendance.start_time, attendance.lunch_start, attendance.lunch_end,
                     attendance.end_time, attendance.standard_hours],
        'calendar': list(WorkCalendarDay.objects.filter(date__year=attendance.year,
            date__month=attendance.month).order_by('date').values('date', 'kind', 'expected_units')),
        'attendance': list(records.order_by('date').values('date', 'check_in', 'check_out', 'status',
            'work_hours', 'late_minutes', 'actual_units', 'paid_leave_units', 'paid_units')),
        'leave': list(LeaveDay.objects.filter(employee=employee, date__year=attendance.year,
            date__month=attendance.month, approved=True).order_by('date').values('date', 'units', 'paid')),
        'overtime': [{key: row[key] for key in ['id','date','start','end','hours','multiplier']} for row in overtime],
        'overtime_policy': 'automatic-checkout-1700-v1',
        'overtime_hourly_rate': inputs.overtime_hourly_rate,
        'overtime_basis':inputs.overtime_basis,
        'bonuses': list(bonuses.order_by('pk').values('id', 'amount')),
        'adjustments': list(adjustments.order_by('pk').values('id', 'kind', 'amount')),
        'insurance_base': inputs.insurance_base,
        'insurance_rates': {key: Decimal(str(rate)) for key, rate in inputs.insurance_rates.items()},
        'tax': inputs.tax_amount,
    })


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
