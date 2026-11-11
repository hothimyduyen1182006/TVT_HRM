from datetime import datetime, time
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from employees.models import Employee
from .models import AttendanceRecord
from .services.clocking import punch
from .services.workflow import period_is_locked
from .services.scheduling import clock_schedule


@login_required
@require_http_methods(['GET', 'POST'])
def today(request):
    employee = Employee.objects.filter(user=request.user, is_active=True).first()
    if not employee:
        raise PermissionDenied('Tài khoản chưa liên kết nhân viên đang làm việc.')
    now = timezone.localtime().replace(microsecond=0)
    if request.method == 'POST':
        try:
            record = punch(request.user, request.POST.get('action'), request.POST.get('note', ''))
            request.session['clock_success'] = {'record': record.pk, 'action': request.POST['action']}
        except ValidationError as error:
            messages.error(request, ' '.join(error.messages))
        return redirect('attendance:clock')
    record = AttendanceRecord.objects.filter(employee=employee, date=now.date()).first()
    schedule = clock_schedule(now.date())
    period, day = schedule['period'], schedule['day']
    locked = period_is_locked(period, employee.pk, now.date()) if period and period.pk else False
    workday = day and day.kind == 'work'
    can_punch = bool(not schedule['error'] and period and period.policy_confirmed and not locked and workday and
                     employee.hire_date <= now.date())
    page_state = 'done' if record and record.check_out else (
        'checkout' if record and record.check_in else 'checkin')
    success = request.session.pop('clock_success', {})
    if not record or success.get('record') != record.pk:
        success = {}
    hours = record.work_hours if record else Decimal(0)
    elapsed_hours = Decimal(0)
    if record and record.check_in and record.check_out:
        elapsed_seconds = (datetime.combine(record.date, record.check_out) -
                           datetime.combine(record.date, record.check_in)).total_seconds()
        elapsed_hours = Decimal(str(elapsed_seconds)) / Decimal(3600)
    if record and record.check_in and not record.check_out and period:
        start = max(datetime.combine(now.date(), record.check_in), datetime.combine(now.date(), period.start_time))
        end = min(now.replace(tzinfo=None), datetime.combine(now.date(), period.end_time),
                  datetime.combine(now.date(), time(17)))
        lunch = max(0, (min(end, datetime.combine(now.date(), period.lunch_end)) - max(start, datetime.combine(now.date(), period.lunch_start))).total_seconds())
        hours = Decimal(str(max(0, (end - start).total_seconds() - lunch))) / Decimal(3600)
    minutes = int(hours * 60)
    return render(request, 'attendance/checkin.html', {
        'employee': employee, 'record': record, 'today_record': record,
        'period': period, 'now': now, 'today': now.date(),
        'success': success.get('action'), 'page_state': page_state,
        'can_check_in': can_punch and record is None,
        'can_check_out': can_punch and bool(record and record.check_in and not record.check_out),
        'locked': locked, 'is_late': bool(record and record.late_minutes),
        'schedule_error': schedule['error'],
        'elapsed_hours': elapsed_hours,
        'duration': f'{minutes // 60:02}:{minutes % 60:02}',
    })
