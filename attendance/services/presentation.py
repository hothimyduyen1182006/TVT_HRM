"""Dữ liệu hiển thị; không thay đổi công thức hoặc tạo bản ghi chấm công."""
import calendar
from datetime import date
from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import Sum, Count, Q, F

from attendance.models import AttendanceRecord, WorkCalendarDay, AttendanceAuditLog
from attendance.models import EmployeeAttendanceApproval, AttendancePeriod, OvertimeApproval
from attendance.forms import AUDIT_FIELDS, AttendanceFilter, DailyFilter, HistoryFilter
from employees.models import Employee

ZERO = Decimal(0)


def overtime_context(request, record):
    from attendance.forms import OvertimeRequestForm, OvertimeApprovalForm, OvertimeRejectionForm
    from .calculations import overtime_candidate, interval_hours
    from .workflow import can_approve_overtime, period_is_locked
    from payroll.models import PayrollPeriod
    period=AttendancePeriod.objects.filter(year=record.date.year,month=record.date.month).first()
    employee=Employee.objects.select_related('department').get(pk=record.employee_id)
    rows=list(OvertimeApproval.objects.filter(employee=employee,date=record.date).select_related(
        'requested_by','reviewed_by','department').order_by('start_time','pk'))
    locked=not period or period_is_locked(period,employee.pk) or PayrollPeriod.objects.filter(attendance_period=period).filter(
        Q(status__in=['approved','paid'])|Q(records__employee_id=employee.pk,records__status__in=['approved','paid'])).exists()
    candidate=overtime_candidate(record,period) if not locked and period and period.policy_confirmed else None
    own=employee.user_id==request.user.pk
    can_submit=bool(own and employee.is_active and employee.department.allows_overtime and candidate)
    initial={'start_time':candidate[0],'end_time':candidate[1]} if candidate else {}
    for row in rows:
        row.approval_form=OvertimeApprovalForm(initial={'hours':row.requested_hours})
    return {'overtime_requests':rows,'can_submit_ot':can_submit,'can_manage_ot':can_approve_overtime(request.user,employee),
        'ot_locked':locked,'ot_request_form':OvertimeRequestForm(initial=initial),'ot_rejection_form':OvertimeRejectionForm(),
        'ot_candidate_hours':interval_hours(record.date,*candidate) if candidate else ZERO,
        'is_production':employee.department.allows_overtime,'is_own_record':own,
        'outside_policy_extra':bool(not employee.department.allows_overtime and period and record.check_out and record.check_out>period.end_time)}


def month_summary(employees, year, month, period):
    scope = employees.values('pk')
    records = AttendanceRecord.objects.filter(employee_id__in=scope, date__year=year, date__month=month)
    grouped = records.values('employee_id').annotate(paid=Sum('paid_units'), actual=Sum('actual_units'),
        leave=Sum('paid_leave_units'), hours=Sum('work_hours'), late=Sum('late_minutes'),
        late_count=Count('pk', filter=Q(late_minutes__gt=0)), count=Count('pk'),
        incomplete=Count('pk', filter=Q(status='incomplete')), absent=Count('pk', filter=Q(status='absent')))
    by_employee = {row['employee_id']: row for row in grouped}
    ot_totals=dict(OvertimeApproval.objects.filter(employee_id__in=scope,date__year=year,date__month=month,
        status='approved',approved=True,approved_by__isnull=False,approved_at__isnull=False,
        requested_at__isnull=False).values('employee_id').annotate(value=Sum('hours')).values_list('employee_id','value'))
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
            'absent': values.get('absent', 0), 'ot': ot_totals.get(employee.pk,ZERO), 'state': state,
            'state_label': {'empty': 'Chưa có dữ liệu', 'approved': 'Đã duyệt', 'pending': 'Chờ duyệt',
                            'incomplete': 'Cần kiểm tra'}[state], 'has_records': bool(values)})
    return result


def daily_rows(employee, year, month):
    records = {r.date: r for r in AttendanceRecord.objects.filter(employee=employee, date__year=year, date__month=month)}
    calendar_days = {r.date: r for r in WorkCalendarDay.objects.filter(date__year=year, date__month=month)}
    ot_totals=dict(OvertimeApproval.objects.filter(employee=employee,date__year=year,date__month=month,
        status='approved',approved=True,approved_by__isnull=False,approved_at__isnull=False,
        requested_at__isnull=False).values('date').annotate(value=Sum('hours')).values_list('date','value'))
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
            'record': record, 'state': state, 'label': label, 'ot': ot_totals.get(value,ZERO)})
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


def month_data(request, employee):
    """Tổng hợp ngày công và bộ lọc cho một nhân viên, không thay đổi dữ liệu."""
    form = DailyFilter(request.user, request.GET)
    rows, summary, period, progress, average = [], None, None, 0, '—'
    month_query = ''
    if form.is_valid():
        data = form.cleaned_data
        month_query = urlencode({'month': data['month'], 'year': data['year']})
        period = AttendancePeriod.objects.filter(year=data['year'], month=data['month']).first()
        summary = month_summary(Employee.objects.filter(pk=employee.pk), data['year'], data['month'], period)[0]
        rows = daily_rows(employee, data['year'], data['month'])
        work_count = sum(1 for row in rows if row['record'] and row['record'].check_in)
        if work_count:
            minutes = int(summary['hours'] * 60 / work_count)
            average = f'{minutes // 60}:{minutes % 60:02}'
        if summary['standard']:
            progress = max(0, min(100, int(summary['paid'] / summary['standard'] * 100)))
        if data['start']:
            rows = [r for r in rows if r['date'] >= data['start']]
        if data['end']:
            rows = [r for r in rows if r['date'] <= data['end']]
        if data['state']:
            state = data['state']
            unit_fields = {'paid': 'paid_units', 'actual': 'actual_units', 'paid_leave': 'paid_leave_units'}
            if state in unit_fields:
                rows = [r for r in rows if r['record'] and getattr(r['record'], unit_fields[state]) > 0]
            else:
                rows = [r for r in rows if r['state'] == state]
    stat_params = request.GET.copy()
    stat_params.pop('page', None)
    stat_params.pop('state', None)
    if form.is_valid():
        stat_params['month'] = form.cleaned_data['month']
        stat_params['year'] = form.cleaned_data['year']
    return {'form': form, 'rows': rows, 'summary': summary, 'period': period, 'progress': progress,
            'average': average, 'month_query': month_query, 'stat_query': stat_params.urlencode()}


def audit_data(request, employee):
    """Lọc lịch sử theo kỳ công và điều kiện người dùng đã chọn."""
    period_form = AttendanceFilter(request.user, request.GET)
    logs = AttendanceAuditLog.objects.none()
    month_query = ''
    if period_form.is_valid():
        data = period_form.cleaned_data
        month_query = urlencode({'month': data['month'], 'year': data['year']})
        logs = history_logs(employee, data['year'], data['month'])
    form = HistoryFilter(request.GET, logs)
    rows = []
    if form.is_valid() and period_form.is_valid():
        data = form.cleaned_data
        if data['start']:
            logs = logs.filter(created_at__date__gte=data['start'])
        if data['end']:
            logs = logs.filter(created_at__date__lte=data['end'])
        if data['actor']:
            logs = logs.filter(actor=data['actor'])
        rows = history_rows(logs, data['field'])
    return {'form': form, 'period_form': period_form, 'rows': rows, 'month_query': month_query}
