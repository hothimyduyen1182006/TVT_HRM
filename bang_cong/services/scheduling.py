"""Kiểm tra ca/lịch thực tế; GET chỉ xem trước, POST mới mở kỳ."""
import calendar
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from bang_cong.models import KyCong, LichLamViec, NhatKyCong

SHIFT_FIELDS = ('gio_bat_dau', 'bat_dau_nghi_trua', 'ket_thuc_nghi_trua', 'gio_ket_thuc', 'gio_chuan')


def validate_schedule(period):
    """Kiểm tra ca và toàn bộ lịch tháng, không phụ thuộc cờ xác nhận cũ."""
    period.full_clean(validate_unique=False, validate_constraints=False)
    days = list(LichLamViec.objects.filter(ngay__year=period.nam, ngay__month=period.thang))
    if len(days) != calendar.monthrange(period.nam, period.thang)[1]:
        raise ValidationError('Lịch chưa đủ tháng; cần cấu hình tất cả ngày trong tháng.')
    for day in days:
        day.full_clean(validate_unique=False, validate_constraints=False)
    return days


def weekly_pattern(source):
    days = validate_schedule(source)
    pattern = {}
    for weekday in range(7):
        choices = {(item.loai_ngay, item.cong_chuan) for item in days
                   if item.ngay.weekday() == weekday and item.loai_ngay != 'holiday'}
        if len(choices) != 1:
            raise ValidationError('Lịch nguồn có ngoại lệ theo tuần; HR cần cấu hình lịch tháng mới để tránh suy đoán sai.')
        pattern[weekday] = choices.pop()
    return pattern


def clock_schedule(day):
    """Trả cấu hình có sẵn hoặc bản xem trước chưa lưu của tháng mới."""
    period = KyCong.objects.filter(nam=day.year, thang=day.month).first()
    scheduled = LichLamViec.objects.filter(ngay=day).first()
    plan = {'period': period, 'day': scheduled, 'source': None, 'weekly': {}, 'error': ''}
    if period:
        try:
            period.full_clean(validate_unique=False, validate_constraints=False)
            if scheduled:
                validate_schedule(period)
        except ValidationError as exc:
            plan['error'] = ' '.join(exc.messages)
            return plan
    if period and scheduled:
        return plan
    if period and (period.trang_thai != 'pending' or period.employee_approvals.exists()):
        plan['error'] = 'Kỳ công đã có dữ liệu duyệt; không tự bổ sung hoặc thay đổi lịch đã khóa.'
        return plan
    source = KyCong.objects.filter(
        Q(nam__lt=day.year) | Q(nam=day.year, thang__lt=day.month)).order_by('-nam', '-thang').first()
    if not source:
        plan['error'] = 'Chưa có ca và lịch làm việc để kế thừa. Vui lòng liên hệ HR.'
        return plan
    try:
        pattern = weekly_pattern(source)
    except ValidationError as exc:
        plan['error'] = ' '.join(exc.messages)
        return plan
    if not period:
        period = KyCong(nam=day.year, thang=day.month,
                                  **{field: getattr(source, field) for field in SHIFT_FIELDS})
    if not scheduled:
        kind, units = pattern[day.weekday()]
        scheduled = LichLamViec(ngay=day, loai_ngay=kind, cong_chuan=units)
    plan.update(period=period, day=scheduled, source=source, weekly=pattern)
    return plan


@transaction.atomic
def ensure_clock_schedule(day, actor):
    plan = clock_schedule(day)
    if plan['error']:
        raise ValidationError(plan['error'])
    if plan['source']:
        KyCong.objects.select_for_update().get(pk=plan['source'].pk)
        plan = clock_schedule(day)  # Kiểm tra lại sau khóa, không ghi từ bản xem trước cũ.
        if plan['error']:
            raise ValidationError(plan['error'])
    preview = plan['period']
    if preview.pk and plan['day'].pk:
        return preview, plan['day']
    period, created = KyCong.objects.get_or_create(nam=day.year, thang=day.month,
        defaults={field: getattr(preview, field) for field in SHIFT_FIELDS})
    period = KyCong.objects.select_for_update().get(pk=period.pk)
    if period.trang_thai != 'pending' or period.employee_approvals.exists():
        raise ValidationError('Kỳ công đã thay đổi hoặc đã khóa. Vui lòng tải lại trang.')
    added = 0
    for number in range(1, calendar.monthrange(day.year, day.month)[1] + 1):
        value = date(day.year, day.month, number)
        kind, units = plan['weekly'][value.weekday()]
        _, new = LichLamViec.objects.get_or_create(ngay=value, defaults={
            'loai_ngay': kind, 'cong_chuan': units, 'ghi_chu': 'Nghỉ hằng tuần' if kind == 'rest' else ''})
        added += new
    validate_schedule(period)
    if created or added:
        NhatKyCong.objects.create(nguoi_thuc_hien=actor, hanh_dong='auto_open_period',
            ly_do='Kế thừa ca và lịch tuần hợp lệ khi nhân viên chấm công', du_lieu_cu={},
            du_lieu_moi={'period': period.pk, 'source_period': plan['source'].pk, 'calendar_days_added': added})
    return period, LichLamViec.objects.get(ngay=day)
