"""Lọc dữ liệu và chuẩn bị nội dung hiển thị; không ghi hoặc tính lại lương."""
import calendar
from datetime import date
from decimal import Decimal

from django.db.models import Sum, Count, Q

from attendance.models import AttendanceRecord
from payroll.models import PayrollRecord, PayrollPeriod, PayrollInput, PayrollAdjustment


def payslip_context(record):
    breakdown = record.breakdown
    insurance = []
    rates = breakdown.get('insurance_rates', {})
    for name, amount in breakdown.get('insurance', {}).items():
        rate = rates.get(name)
        insurance.append({'name': name, 'amount': Decimal(str(amount)),
                          'percent': Decimal(str(rate)) * 100 if rate is not None else None})
    # Model hiện không phân loại riêng phạt đi trễ. Không lấy tổng deductions giả làm phạt.
    # Giữ tổng khấu trừ đã lưu; chi tiết khoản được duyệt nằm trong breakdown.adjustments.
    total_income = record.attendance_pay + record.bonus_pay + record.allowance
    historical_overtime = bool(record.ot_hours or record.ot_pay)
    if historical_overtime:
        total_income += record.ot_pay  # Đối chiếu phiếu cũ; tuyệt đối không tính lại số tiền đã lưu.
    total_deductions = record.insurance + record.tax + record.deductions
    metrics = {'actual': None, 'absent': None, 'late_count': None}
    period = record.period
    attendance = period.attendance_period
    employee_approved = attendance.employee_approvals.filter(employee_id=record.employee_id).exists()
    if attendance.status == 'approved' or employee_approved:
        data = AttendanceRecord.objects.filter(employee_id=record.employee_id,
            date__year=attendance.year, date__month=attendance.month).aggregate(
                actual=Sum('actual_units'), absent=Count('pk', filter=Q(status='absent')),
                late_count=Count('pk', filter=Q(late_minutes__gt=0)))
        metrics = data
    return {'row': record, 'income_total': total_income, 'historical_overtime': historical_overtime,
            'deductions_total': total_deductions,
            'insurance_lines': insurance, 'metrics': metrics,
            'adjustments': breakdown.get('adjustments', []),
            'payment_label': {'pending': 'Chờ duyệt · Chưa chi trả',
                              'approved': 'Đã duyệt · Chưa chi trả', 'paid': 'Đã chi trả'}[record.status]}


def scoped_records(user, form):
    """Giữ phạm vi nhân viên được phép xem trước khi áp dụng bộ lọc lương."""
    if not form.is_valid():
        return PayrollRecord.objects.none()
    data = form.cleaned_data
    rows = PayrollRecord.objects.select_related('period__attendance_period').filter(
        employee__in=form.employee_scope(user), period__attendance_period__month=data['month'],
        period__attendance_period__year=data['year'])
    if data.get('q'):
        rows = rows.filter(Q(employee_name__icontains=data['q']) | Q(employee_code__icontains=data['q']))
    if data.get('status'):
        rows = rows.filter(status=data['status'])
    return rows


def employee_records(user):
    """Phiếu lương của tài khoản hiện tại, không mở rộng theo vai trò quản lý."""
    return PayrollRecord.objects.select_related('period__attendance_period').filter(employee__user=user)


def input_list_context(user, form):
    """Chuẩn bị đầu vào thuế, bảo hiểm, phụ cấp và trạng thái khóa cho giao diện."""
    period, employee_rows = None, []
    input_rows, adjustments = PayrollInput.objects.none(), PayrollAdjustment.objects.none()
    counts = {'total': 0, 'missing': 0, 'draft': 0, 'verified': 0, 'locked': 0}
    if form.is_valid():
        data = form.cleaned_data
        scope = form.employee_scope(user)
        scope = scope.filter(hire_date__lte=date(data['year'], data['month'], calendar.monthrange(data['year'], data['month'])[1]))
        if data['q']:
            scope = scope.filter(Q(code__icontains=data['q']) | Q(full_name__icontains=data['q']))
        period = PayrollPeriod.objects.select_related('attendance_period').filter(
            attendance_period__month=data['month'], attendance_period__year=data['year']).first()
        if period:
            input_rows = PayrollInput.objects.select_related('employee', 'period').filter(period=period, employee__in=scope)
            adjustments = PayrollAdjustment.objects.select_related('employee', 'period').filter(period=period, employee__in=scope).order_by('employee__code', 'kind', 'name')
            by_employee = {item.employee_id: item for item in input_rows}
            salary_statuses = dict(period.records.values_list('employee_id', 'status'))
            for employee in scope:
                item = by_employee.get(employee.pk)
                locked = period.status != 'pending' or salary_statuses.get(employee.pk) in ['approved', 'paid']
                state = 'locked' if locked else ('missing' if item is None else ('verified' if item.verified else 'draft'))
                counts['total'] += 1
                counts[state] += 1
                if data['readiness'] and data['readiness'] != state:
                    continue
                rates = [{'name': name, 'percent': Decimal(str(rate)) * 100} for name, rate in item.insurance_rates.items()] if item else []
                employee_rows.append({'employee': employee, 'input': item, 'locked': locked, 'state': state,
                    'state_label': {'missing': 'Chưa nhập', 'draft': 'Chưa kiểm tra', 'verified': 'Đã kiểm tra', 'locked': 'Đã khóa'}[state],
                    'rates': rates, 'salary_status': salary_statuses.get(employee.pk)})
            if data['readiness']:
                adjustments = adjustments.filter(employee_id__in=[row['employee'].pk for row in employee_rows])
            for item in adjustments:
                item.ui_locked = period.status != 'pending' or salary_statuses.get(item.employee_id) in ['approved', 'paid']
    return {'form': form, 'period': period, 'employee_rows': employee_rows,
        'inputs': input_rows, 'adjustments': adjustments, 'counts': counts,
        'month_label': str(form['month'].value()).zfill(2), 'year_label': form['year'].value()}
