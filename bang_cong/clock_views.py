from datetime import datetime, time
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from nhan_vien.models import Employee

from .models import ChamCong
from .services.clocking import punch
from .services.scheduling import clock_schedule
from .services.workflow import period_is_locked


def _calculate_work_hours(record, now, period):
    """Tính giờ làm đã ghi nhận và giờ làm tạm tính trong ngày."""
    hours = record.so_gio_lam if record else Decimal(0)
    elapsed_hours = Decimal(0)

    if not record or not record.gio_vao:
        return hours, elapsed_hours

    check_in = datetime.combine(record.ngay, record.gio_vao)

    # Đã check-out: hiển thị tổng thời gian thực tế giữa hai lần chấm công.
    if record.gio_ra:
        check_out = datetime.combine(record.ngay, record.gio_ra)
        elapsed_seconds = (check_out - check_in).total_seconds()
        elapsed_hours = Decimal(str(elapsed_seconds)) / Decimal(3600)
        return hours, elapsed_hours

    # Chưa check-out: tạm tính đến hiện tại, giới hạn trong ca và trước 17 giờ.
    if period:
        day = now.date()
        shift_start = datetime.combine(day, period.gio_bat_dau)
        shift_end = datetime.combine(day, period.gio_ket_thuc)
        start = max(check_in, shift_start)
        end = min(now.replace(tzinfo=None), shift_end, datetime.combine(day, time(17)))

        lunch_start = datetime.combine(day, period.bat_dau_nghi_trua)
        lunch_end = datetime.combine(day, period.ket_thuc_nghi_trua)
        lunch_seconds = max(
            0,
            (min(end, lunch_end) - max(start, lunch_start)).total_seconds(),
        )
        worked_seconds = max(0, (end - start).total_seconds() - lunch_seconds)
        hours = Decimal(str(worked_seconds)) / Decimal(3600)

    return hours, elapsed_hours


@login_required
@require_http_methods(['GET', 'POST'])
def today(request):
    # Chỉ cho nhân viên đang hoạt động vào trang chấm công cá nhân.
    employee = Employee.objects.filter(user=request.user, is_active=True).first()
    if not employee:
        raise PermissionDenied('Tài khoản chưa liên kết nhân viên đang làm việc.')

    now = timezone.localtime().replace(microsecond=0)

    # Xử lý chấm công xong thì quay lại trang để tải trạng thái mới.
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            record = punch(request.user, action, request.POST.get('note', ''))
            request.session['clock_success'] = {'record': record.pk, 'action': action}
        except ValidationError as error:
            messages.error(request, ' '.join(error.messages))
        return redirect('bang_cong:clock')

    # Lấy bản ghi hôm nay và lịch làm việc tương ứng.
    record = ChamCong.objects.filter(nhan_vien=employee, ngay=now.date()).first()
    schedule = clock_schedule(now.date())
    period, day = schedule['period'], schedule['day']
    locked = period_is_locked(period, employee.pk, now.date()) if period and period.pk else False
    workday = day and day.loai_ngay == 'work'
    can_punch = bool(
        not schedule['error']
        and period
        and not locked
        and workday
        and employee.hire_date <= now.date()
    )

    # Chỉ hiện thông báo thành công nếu nó thuộc đúng bản ghi đang xem.
    page_state = 'done' if record and record.gio_ra else (
        'checkout' if record and record.gio_vao else 'checkin'
    )
    success = request.session.pop('clock_success', {})
    if not record or success.get('record') != record.pk:
        success = {}
    hours, elapsed_hours = _calculate_work_hours(record, now, period)
    minutes = int(hours * 60)

    # Giữ nguyên các tên context mà trang chấm công hiện đang sử dụng.
    return render(request, 'attendance/checkin.html', {
        'employee': employee, 'record': record, 'today_record': record,
        'period': period, 'now': now, 'today': now.date(),
        'success': success.get('action'), 'page_state': page_state,
        'can_check_in': can_punch and record is None,
        'can_check_out': can_punch and bool(record and record.gio_vao and not record.gio_ra),
        'locked': locked, 'is_late': bool(record and record.so_phut_tre),
        'schedule_error': schedule['error'],
        'elapsed_hours': elapsed_hours,
        'duration': f'{minutes // 60:02}:{minutes % 60:02}',
    })
