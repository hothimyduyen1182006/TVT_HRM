"""Dữ liệu hiển thị; không thay đổi công thức hoặc tạo bản ghi chấm công."""
import calendar
from datetime import date
from decimal import Decimal
from django.db.models import Sum, Count, Q, F
from attendance.models import AttendanceRecord, WorkCalendarDay, OvertimeApproval, AttendanceAuditLog
from attendance.models import EmployeeAttendanceApproval
from attendance.forms import AUDIT_FIELDS

ZERO = Decimal(0)


def month_summary(employees, year, month, period):
    scope = employees.values('pk')
    records = AttendanceRecord.objects.filter(employee_id__in=scope, date__year=year, date__month=month)
    grouped = records.values('employee_id').annotate(paid=Sum('paid_units'), actual=Sum('actual_units'),
        leave=Sum('paid_leave_units'), hours=Sum('work_hours'), late=Sum('late_minutes'),
        late_count=Count('pk', filter=Q(late_minutes__gt=0)), count=Count('pk'),
        incomplete=Count('pk', filter=Q(status='incomplete')), absent=Count('pk', filter=Q(status='absent')))
    by_employee = {row['employee_id']: row for row in grouped}
    overtime = OvertimeApproval.objects.filter(employee_id__in=scope, date__year=year, date__month=month,
        approved=True, approved_by__isnull=False, approved_at__isnull=False)
    ot = {row['employee_id']: row['hours'] for row in overtime.values('employee_id').annotate(hours=Sum('hours'))}
    standard = WorkCalendarDay.objects.filter(date__year=year, date__month=month).aggregate(value=Sum('expected_units'))['value']
    result = []
    approved_ids = set(EmployeeAttendanceApproval.objects.filter(period=period).values_list('employee_id', flat=True)) if period else set()
    for employee in employees:
        values = by_employee.get(employee.pk, {})
        state = 'empty' if not values else ('approved' if employee.pk in approved_ids or (period and period.status == 'approved')
                else ('incomplete' if values['incomplete'] else 'pending'))
        result.append({'employee': employee, 'standard': standard, 'paid': values.get('paid', ZERO),
            'actual': values.get('actual', ZERO), 'leave': values.get('leave', ZERO),
            'hours': values.get('hours', ZERO), 'late': values.get('late', 0), 'late_count': values.get('late_count', 0),
            'absent': values.get('absent', 0), 'ot': ot.get(employee.pk, ZERO), 'state': state,
            'state_label': {'empty': 'Chưa có dữ liệu', 'approved': 'Đã duyệt', 'pending': 'Chờ duyệt',
                            'incomplete': 'Cần kiểm tra'}[state], 'has_records': bool(values)})
    return result


def daily_rows(employee, year, month):
    records = {r.date: r for r in AttendanceRecord.objects.filter(employee=employee, date__year=year, date__month=month)}
    calendar_days = {r.date: r for r in WorkCalendarDay.objects.filter(date__year=year, date__month=month)}
    overtime = {r.date: r.hours for r in OvertimeApproval.objects.filter(employee=employee,
        date__year=year, date__month=month, approved=True, approved_by__isnull=False, approved_at__isnull=False)}
    result = []
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        value = date(year, month, day)
        if value < employee.hire_date:
            continue
        record, schedule = records.get(value), calendar_days.get(value)
        state, label = 'incomplete', 'Chưa có dữ liệu'
        if record:
            if record.status == 'present':
                state, label = ('late', 'Đi làm trễ') if record.late_minutes else ('present', 'Đi đúng giờ')
            elif record.status == 'leave':
                state, label = 'leave', 'Nghỉ có lương' if record.paid_leave_units else 'Nghỉ không lương'
            elif record.status == 'absent':
                state, label = 'absent', 'Nghỉ không phép'
            else:
                label = 'Thiếu dữ liệu'
        elif schedule and schedule.kind != 'work':
            state = 'rest'
            label = schedule.name or ('Nghỉ lễ' if schedule.kind == 'holiday' else 'Nghỉ hằng tuần')
        result.append({'date': value, 'weekday': ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'][value.weekday()],
            'record': record, 'state': state, 'label': label, 'ot': overtime.get(value, ZERO)})
    return result


def history_logs(employee, year, month):
    # save_record là tên sự kiện cũ: chỉ giữ lần sửa có cả trước/sau, không lấy lần tạo.
    return AttendanceAuditLog.objects.filter(action__in=['edit_record', 'save_record'],
        after__employee_id=str(employee.pk), after__date__startswith=f'{year:04}-{month:02}-'
        ).exclude(before={}).exclude(before=F('after')).select_related('actor').order_by('-created_at', '-pk')


def history_rows(logs, field=''):
    result = []
    labels = dict(AttendanceRecord._meta.get_field('status').choices)
    labels.update({'pending': 'Chờ duyệt', 'approved': 'Đã duyệt'})
    for log in logs:
        if log.action not in ['edit_record', 'save_record'] or not log.before or log.before == log.after:
            continue
        for key, title in AUDIT_FIELDS.items():
            old, new = log.before.get(key, ''), log.after.get(key, '')
            if old == new or (field and field != key):
                continue
            result.append({'time': log.created_at, 'date': log.after.get('date'), 'field': title,
                'old': labels.get(old, old) if key in ['status', 'approval_status'] else old,
                'new': labels.get(new, new) if key in ['status', 'approval_status'] else new,
                'actor': log.actor.get_full_name() or log.actor.username, 'reason': log.reason})
    return result
