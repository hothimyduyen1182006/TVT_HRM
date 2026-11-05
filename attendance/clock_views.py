from datetime import datetime
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from employees.models import Employee
from .models import AttendanceRecord, AttendancePeriod
from .services.clocking import punch


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
    period = AttendancePeriod.objects.filter(year=now.year, month=now.month).first()
    success = request.session.pop('clock_success', {})
    if not record or success.get('record') != record.pk:
        success = {}
    hours = record.work_hours if record else Decimal(0)
    if record and record.check_in and not record.check_out and period:
        start = max(datetime.combine(now.date(), record.check_in), datetime.combine(now.date(), period.start_time))
        end = min(now.replace(tzinfo=None), datetime.combine(now.date(), period.end_time))
        lunch = max(0, (min(end, datetime.combine(now.date(), period.lunch_end)) - max(start, datetime.combine(now.date(), period.lunch_start))).total_seconds())
        hours = Decimal(str(max(0, (end - start).total_seconds() - lunch))) / Decimal(3600)
    minutes = int(hours * 60)
    return render(request, 'attendance/clock.html', {'employee': employee, 'record': record,
        'period': period, 'now': now, 'success': success.get('action'),
        'duration': f'{minutes // 60:02}:{minutes % 60:02}'})
