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
from .source_data import source_data, canonical
from .tax import calculate_tax

ZERO = Decimal(0)


def total(queryset, field):
    return queryset.aggregate(value=Sum(field))['value'] or ZERO


def snapshot(period):
    return [{k: str(v) for k, v in row.items()} for row in period.records.values()]


def recalculation_records(period, attendance=None):
    """Phiếu chờ duyệt sẽ bị thay thế trong lần tính này."""
    attendance = attendance or period.attendance_period
    employee_ids = (attendance.employee_ids if attendance.status == 'approved'
                    else attendance.employee_approvals.values_list('employee_id', flat=True))
    return period.records.filter(status='pending', employee_id__in=employee_ids)


@transaction.atomic
def calculate_payroll(actor, period_id, reason):
    require_role(actor, HR, DIRECTOR)
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
    replacing = recalculation_records(period, attendance)
    reason = reason.strip()
    if replacing.exists() and not reason:
        raise ValidationError('Cần ghi lý do tính lại lương.')
    reason = reason or f'Tạo phiếu lương mới kỳ {attendance.month:02}/{attendance.year}'
    PayrollAuditLog.objects.create(period=period, actor=actor, action='before_calculate', reason=reason, snapshot=snapshot(period))
    replacing.delete()
    for employee in employees.select_related('department'):
        if period.records.filter(employee=employee, status__in=['approved', 'paid']).exists():
            continue  # Giữ nguyên phiếu đã duyệt khi tính lại phần còn chờ duyệt.
        PayrollRecord.objects.create(**payroll_values(employee, attendance, period, standard))
    period.attendance_revision = attendance.revision
    period.save()
    PayrollAuditLog.objects.create(period=period, actor=actor, action='calculate', reason=reason, snapshot=snapshot(period))
    return period


@transaction.atomic
def refresh_employee_payroll(actor, employee_id, year, month):
    """Cập nhật đúng một nhân viên/kỳ sau thao tác lưu nguồn đã được phân quyền."""
    from .workflow import record_approval_error
    require_role(actor, HR, DIRECTOR)
    attendance = AttendancePeriod.objects.select_for_update().filter(year=year, month=month).first()
    if not attendance:
        return ''
    approved = (employee_id in attendance.employee_ids if attendance.status == 'approved' else
                attendance.employee_approvals.filter(employee_id=employee_id).exists())
    if not approved:
        return ''  # Chờ duyệt công, không tự duyệt hoặc dùng công chưa xác nhận.
    period, _ = PayrollPeriod.objects.get_or_create(attendance_period=attendance)
    period = PayrollPeriod.objects.select_for_update().get(pk=period.pk)
    if period.status != 'pending':
        return ''
    row = period.records.select_for_update().filter(employee_id=employee_id).first()
    if row and row.status != 'pending':
        return ''
    employee = Employee.objects.select_related('department').get(pk=employee_id)
    same_identity = row and (row.employee_code, row.employee_name, row.department_id_snapshot, row.department_name) == (
        employee.code, employee.full_name, employee.department_id, employee.department.name)
    if same_identity and not record_approval_error(row, period, attendance):
        return ''
    try:
        values = payroll_values(employee, attendance, period)
    except ValidationError as exc:
        return f'{employee.code}: ' + '; '.join(exc.messages)
    before = [{k: str(v) for k, v in item.items()} for item in period.records.filter(employee_id=employee_id).values()]
    row, _ = PayrollRecord.objects.update_or_create(period=period, employee=employee, defaults=values)
    period.attendance_revision = attendance.revision
    period.save(update_fields=['attendance_revision'])
    after = [{k: str(v) for k, v in item.items()} for item in period.records.filter(pk=row.pk).values()]
    PayrollAuditLog.objects.create(period=period, actor=actor, action='auto_calculate',
        reason=f'Tự cập nhật lương {employee.code} sau thay đổi dữ liệu nguồn',
        snapshot=[{'before': before, 'after': after}])
    return ''


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
    tax_details = calculate_tax(inputs, attendance, wage, ot_pay, bonus, insurance, adjustments, overtime)
    tax = tax_details['tax']
    net = wage + ot_pay + bonus + allowance - insurance - tax - deductions
    values = dict(
        period=period, employee=employee, employee_code=employee.code, employee_name=employee.full_name,
        department_id_snapshot=employee.department_id, department_name=employee.department.name,
        base_salary=employee.base_salary, standard_units=standard, paid_units=paid,
        leave_units=total(LeaveDay.objects.filter(employee=employee, date__year=attendance.year,
                                                 date__month=attendance.month, approved=True), 'units'),
        late_minutes=total(records, 'late_minutes'), ot_hours=sum((row['hours'] for row in overtime),ZERO), attendance_pay=wage,
        ot_pay=ot_pay, bonus_pay=bonus, allowance=allowance, insurance=insurance, tax=tax,
        deductions=deductions, net_pay=net.quantize(Decimal('1'), rounding=ROUND_HALF_UP),
        breakdown={'attendance_revision': attendance.revision,
                   'ot': ot_lines, 'overtime_warnings': [warning for row in overtime for warning in row['warnings']], 'bonuses': bonus_lines, 'insurance': insurance_lines,
                   'overtime_hourly_rate':str(ot_rate),'overtime_basis':inputs.overtime_basis,
                   'insurance_base': str(inputs.insurance_base), 'insurance_rates': inputs.insurance_rates,
                   'tax_basis': inputs.tax_basis, 'tax_calculation': canonical(tax_details), 'insurance_basis': inputs.insurance_basis,
                   'hourly_rate': str(hourly), 'attendance_pay_exact': str(wage), 'net_exact': str(net),
                   'adjustments': [{'id': row.pk, 'name': row.name, 'kind': row.kind,
                                    'amount': str(row.amount), 'basis': row.basis} for row in adjustments]})

    values['breakdown']['source_data'] = source_data(employee, attendance, inputs, records, overtime, bonuses, adjustments, tax_details)
    return values
