from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from employees.access import require_role, HR, DIRECTOR
from employees.models import Employee
from attendance.models import AttendancePeriod, AttendanceRecord, WorkCalendarDay
from bonuses.models import Bonus, payroll_bonus_records
from leaves.models import LeaveDay
from payroll.models import PayrollPeriod, PayrollInput, PayrollAdjustment, PayrollRecord, PayrollAuditLog
from .source_data import source_data

ZERO = Decimal(0)


def total(queryset, field):
    return queryset.aggregate(value=Sum(field))['value'] or ZERO


def snapshot(period):
    return [{k: str(v) for k, v in row.items()} for row in period.records.values()]


@transaction.atomic
def calculate_payroll(actor, period_id, reason):
    require_role(actor, HR, DIRECTOR)
    if not reason.strip():
        raise ValidationError('Cần ghi lý do tính lương.')
    # Cùng thứ tự khóa với workflow công: kỳ công trước, kỳ lương sau.
    link = PayrollPeriod.objects.get(pk=period_id)
    attendance = AttendancePeriod.objects.select_for_update().get(pk=link.attendance_period_id)
    period = PayrollPeriod.objects.select_for_update().get(pk=period_id)
    if period.status != 'pending':
        raise ValidationError('Không tính lại lương đã duyệt/chi trả.')
    approved_ids = list(attendance.employee_approvals.values_list('employee_id', flat=True))
    if attendance.status != 'approved' and not approved_ids:
        raise ValidationError('Chưa có nhân viên được duyệt bảng công trong kỳ.')
    standard = total(WorkCalendarDay.objects.filter(date__year=attendance.year, date__month=attendance.month), 'expected_units')
    if standard <= 0 or attendance.standard_hours <= 0:
        raise ValidationError('Công chuẩn phải lớn hơn 0.')
    employee_ids = attendance.employee_ids if attendance.status == 'approved' else approved_ids
    employees = Employee.objects.filter(pk__in=employee_ids)
    if not employees.exists():
        raise ValidationError('Không có nhân viên trong kỳ.')
    PayrollAuditLog.objects.create(period=period, actor=actor, action='before_calculate', reason=reason, snapshot=snapshot(period))
    period.records.filter(status='pending', employee__in=employees).delete()
    for employee in employees.select_related('department'):
        if period.records.filter(employee=employee, status__in=['approved', 'paid']).exists():
            continue  # Giữ nguyên phiếu đã duyệt khi tính lại phần còn chờ duyệt.
        PayrollRecord.objects.create(**payroll_values(employee, attendance, period, standard))
    period.attendance_revision = attendance.revision
    period.save()
    PayrollAuditLog.objects.create(period=period, actor=actor, action='calculate', reason=reason, snapshot=snapshot(period))
    return period


def payroll_values(employee, attendance, period, standard=None):
    """Tính trong bộ nhớ để tạo hoặc đối chiếu phiếu; không ghi dữ liệu."""
    if standard is None:
        standard = total(WorkCalendarDay.objects.filter(date__year=attendance.year, date__month=attendance.month), 'expected_units')
    if standard <= 0 or attendance.standard_hours <= 0:
        raise ValidationError('Công chuẩn phải lớn hơn 0.')
    inputs = PayrollInput.objects.filter(period=period, employee=employee, verified=True).first()
    if inputs is None:
        raise ValidationError(f'{employee}: thiếu dữ liệu thuế/BH đã kiểm tra.')
    inputs.full_clean()
    records = AttendanceRecord.objects.filter(employee=employee, date__year=attendance.year, date__month=attendance.month)
    paid = total(records, 'paid_units')
    hourly = employee.base_salary / standard / attendance.standard_hours
    wage = employee.base_salary / standard * paid
    from attendance.services.calculations import payroll_overtime
    overtime=payroll_overtime(employee,attendance.year,attendance.month)
    if overtime and (not inputs.overtime_hourly_rate or not inputs.overtime_basis.strip()):
        raise ValidationError(f'{employee}: HR cần nhập lương giờ căn cứ OT và căn cứ áp dụng trước khi tính lương.')
    ot_rate=inputs.overtime_hourly_rate or ZERO
    ot_lines=[{**{key: str(row[key]) if key in ['hours','multiplier'] else row[key]
                     for key in ['id','date','start','end','hours','multiplier']},
               'amount': str(ot_rate * row['hours'] * row['multiplier'])} for row in overtime]
    ot_pay=sum((Decimal(item['amount']) for item in ot_lines),ZERO)
    bonuses = payroll_bonus_records(Bonus.objects.filter(
        employee=employee, year=attendance.year, month=attendance.month))
    bonus_lines = [{'id': row.pk, 'name': row.name, 'amount': str(row.amount)} for row in bonuses]
    bonus = sum((Decimal(line['amount']) for line in bonus_lines), ZERO)
    adjustments = PayrollAdjustment.objects.filter(employee=employee, period=period, approved=True)
    allowance = total(adjustments.filter(kind='allowance'), 'amount')
    deductions = total(adjustments.filter(kind='deduction'), 'amount')
    insurance_lines = {name: str(inputs.insurance_base * Decimal(str(rate)))
                       for name, rate in inputs.insurance_rates.items()}
    insurance = sum((Decimal(value) for value in insurance_lines.values()), ZERO)
    net = wage + ot_pay + bonus + allowance - insurance - inputs.tax_amount - deductions
    values = dict(
        period=period, employee=employee, employee_code=employee.code, employee_name=employee.full_name,
        department_id_snapshot=employee.department_id, department_name=employee.department.name,
        base_salary=employee.base_salary, standard_units=standard, paid_units=paid,
        leave_units=total(LeaveDay.objects.filter(employee=employee, date__year=attendance.year,
                                                 date__month=attendance.month, approved=True), 'units'),
        late_minutes=total(records, 'late_minutes'), ot_hours=sum((row['hours'] for row in overtime),ZERO), attendance_pay=wage,
        ot_pay=ot_pay, bonus_pay=bonus, allowance=allowance, insurance=insurance, tax=inputs.tax_amount,
        deductions=deductions, net_pay=net.quantize(Decimal('1'), rounding=ROUND_HALF_UP),
        breakdown={'attendance_revision': attendance.revision,
                   'ot': ot_lines, 'overtime_warnings': [warning for row in overtime for warning in row['warnings']], 'bonuses': bonus_lines, 'insurance': insurance_lines,
                   'overtime_hourly_rate':str(ot_rate),'overtime_basis':inputs.overtime_basis,
                   'insurance_base': str(inputs.insurance_base), 'insurance_rates': inputs.insurance_rates,
                   'tax_basis': inputs.tax_basis, 'insurance_basis': inputs.insurance_basis,
                   'hourly_rate': str(hourly), 'attendance_pay_exact': str(wage), 'net_exact': str(net),
                   'adjustments': [{'id': row.pk, 'name': row.name, 'kind': row.kind,
                                    'amount': str(row.amount), 'basis': row.basis} for row in adjustments]})

    values['breakdown']['source_data'] = source_data(employee, attendance, inputs, records, overtime, bonuses, adjustments)
    return values
