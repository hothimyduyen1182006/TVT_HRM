"""Nhận thao tác chấm công và chuẩn bị dữ liệu hiển thị trong ngày."""

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
from .services.cham_cong import ghi_nhan_cham_cong, xem_lich_cham_cong
from .services.quy_trinh import ky_cong_da_khoa


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
def cham_cong_hom_nay(request):
    nhan_vien = Employee.objects.filter(user=request.user, is_active=True).first()
    if not nhan_vien:
        raise PermissionDenied('Tài khoản chưa liên kết nhân viên đang làm việc.')
    hien_tai = timezone.localtime().replace(microsecond=0)
    hom_nay = hien_tai.date()

    if request.method == 'POST':
        thao_tac = request.POST.get('action')
        try:
            ban_ghi = ghi_nhan_cham_cong(request.user, thao_tac, request.POST.get('note', ''))
            request.session['clock_success'] = {'record': ban_ghi.pk, 'action': thao_tac}
        except ValidationError as loi:
            messages.error(request, ' '.join(loi.messages))
        return redirect('bang_cong:cham-cong')

    ban_ghi = ChamCong.objects.filter(nhan_vien=nhan_vien, ngay=hom_nay).first()
    ke_hoach = xem_lich_cham_cong(hom_nay)
    ky_cong, lich_ngay = ke_hoach['period'], ke_hoach['day']
    da_khoa = ky_cong_da_khoa(ky_cong, nhan_vien.pk, hom_nay) if ky_cong and ky_cong.pk else False
    duoc_cham_cong = bool(
        not ke_hoach['error'] and ky_cong and not da_khoa
        and lich_ngay and lich_ngay.loai_ngay == 'work' and nhan_vien.hire_date <= hom_nay
    )
    dang_trong_ca = bool(ban_ghi and ban_ghi.gio_vao and not ban_ghi.gio_ra)
    trang_thai_trang = 'done' if ban_ghi and ban_ghi.gio_ra else (
        'checkout' if ban_ghi and ban_ghi.gio_vao else 'checkin')
    thanh_cong = request.session.pop('clock_success', {})
    if not ban_ghi or thanh_cong.get('record') != ban_ghi.pk:
        thanh_cong = {}

    so_gio, tong_gio_vao_ra = _calculate_work_hours(ban_ghi, hien_tai, ky_cong)
    so_phut = int(so_gio * 60)

    return render(request, 'attendance/checkin.html', {
        'employee': nhan_vien, 'record': ban_ghi, 'today_record': ban_ghi,
        'period': ky_cong, 'now': hien_tai, 'today': hom_nay,
        'success': thanh_cong.get('action'), 'page_state': trang_thai_trang,
        'can_check_in': duoc_cham_cong and ban_ghi is None,
        'can_check_out': duoc_cham_cong and dang_trong_ca,
        'locked': da_khoa, 'is_late': bool(ban_ghi and ban_ghi.so_phut_tre),
        'schedule_error': ke_hoach['error'], 'elapsed_hours': tong_gio_vao_ra,
        'duration': f'{so_phut // 60:02}:{so_phut % 60:02}',
    })
