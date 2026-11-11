"""Kế thừa ca/lịch tuần đã xác nhận; GET chỉ xem trước, POST mới mở kỳ."""
import calendar
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from attendance.models import AttendancePeriod, WorkCalendarDay, AttendanceAuditLog

SHIFT_FIELDS = ('start_time', 'lunch_start', 'lunch_end', 'end_time', 'standard_hours')


def weekly_pattern(source):
    days = list(WorkCalendarDay.objects.filter(date__year=source.year, date__month=source.month))
    if len(days) != calendar.monthrange(source.year, source.month)[1]:
        raise ValidationError('Lịch nguồn chưa đủ tháng; HR cần xác nhận lịch làm việc trước.')
    pattern = {}
    for weekday in range(7):
        choices = {(item.kind, item.expected_units) for item in days
                   if item.date.weekday() == weekday and item.kind != 'holiday'}
        if len(choices) != 1:
            raise ValidationError('Lịch nguồn có ngoại lệ theo tuần; HR cần cấu hình lịch tháng mới để tránh suy đoán sai.')
        pattern[weekday] = choices.pop()
    return pattern


def clock_schedule(day):
    """Trả cấu hình có sẵn hoặc bản xem trước chưa lưu của tháng mới."""
    period = AttendancePeriod.objects.filter(year=day.year, month=day.month).first()
    scheduled = WorkCalendarDay.objects.filter(date=day).first()
    plan = {'period': period, 'day': scheduled, 'source': None, 'weekly': {}, 'error': ''}
    if period and not period.policy_confirmed:
        plan['error'] = 'Ca làm việc hiện tại chưa được HR xác nhận.'
        return plan
    if period and scheduled:
        return plan
    if period and (period.status != 'pending' or period.employee_approvals.exists()):
        plan['error'] = 'Kỳ công đã có dữ liệu duyệt; không tự bổ sung hoặc thay đổi lịch đã khóa.'
        return plan
    source = AttendancePeriod.objects.filter(
        Q(year__lt=day.year) | Q(year=day.year, month__lt=day.month)).order_by('-year', '-month').first()
    if not source or not source.policy_confirmed:
        plan['error'] = 'Chưa có ca và lịch làm việc đã xác nhận để kế thừa. Vui lòng liên hệ HR.'
        return plan
    try:
        source.full_clean()
        pattern = weekly_pattern(source)
    except ValidationError as exc:
        plan['error'] = ' '.join(exc.messages)
        return plan
    if not period:
        period = AttendancePeriod(year=day.year, month=day.month, policy_confirmed=True,
                                  **{field: getattr(source, field) for field in SHIFT_FIELDS})
    if not scheduled:
        kind, units = pattern[day.weekday()]
        scheduled = WorkCalendarDay(date=day, kind=kind, expected_units=units)
    plan.update(period=period, day=scheduled, source=source, weekly=pattern)
    return plan


@transaction.atomic
def ensure_clock_schedule(day, actor):
    plan = clock_schedule(day)
    if plan['error']:
        raise ValidationError(plan['error'])
    if plan['source']:
        AttendancePeriod.objects.select_for_update().get(pk=plan['source'].pk)
        plan = clock_schedule(day)  # Kiểm tra lại sau khóa, không ghi từ bản xem trước cũ.
        if plan['error']:
            raise ValidationError(plan['error'])
    preview = plan['period']
    if preview.pk and plan['day'].pk:
        return preview, plan['day']
    period, created = AttendancePeriod.objects.get_or_create(year=day.year, month=day.month,
        defaults={**{field: getattr(preview, field) for field in SHIFT_FIELDS}, 'policy_confirmed': True})
    period = AttendancePeriod.objects.select_for_update().get(pk=period.pk)
    if not period.policy_confirmed or period.status != 'pending' or period.employee_approvals.exists():
        raise ValidationError('Kỳ công đã thay đổi hoặc đã khóa. Vui lòng tải lại trang.')
    added = 0
    for number in range(1, calendar.monthrange(day.year, day.month)[1] + 1):
        value = date(day.year, day.month, number)
        kind, units = plan['weekly'][value.weekday()]
        _, new = WorkCalendarDay.objects.get_or_create(date=value, defaults={
            'kind': kind, 'expected_units': units, 'name': 'Nghỉ hằng tuần' if kind == 'rest' else ''})
        added += new
    if created or added:
        AttendanceAuditLog.objects.create(actor=actor, action='auto_open_period',
            reason='Kế thừa ca và lịch tuần đã xác nhận khi nhân viên chấm công', before={},
            after={'period': period.pk, 'source_period': plan['source'].pk, 'calendar_days_added': added})
    return period, WorkCalendarDay.objects.get(date=day)
