"""Xử lý request Bảng lương; tách truy vấn hiển thị khỏi thao tác ghi dữ liệu."""
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from nhan_vien.access import visible_employees, has_role, require_role, HR, DIRECTOR, MANAGER
from .models import Luong, PayrollPeriod
from .forms import BoLocBangLuong, BoLocPhieuLuong
from .services.tinh_toan import tinh_bang_luong
from .services.quy_trinh import xu_ly_trang_thai_luong, duyet_phieu_luong, loi_duyet_luong
from .services.hien_thi import (
    xuat_du_lieu_luong, du_lieu_hien_thi_luong, phieu_luong_du_cong_duyet,
    phieu_luong_trong_pham_vi, phieu_luong_ca_nhan,
)


def _ve_danh_sach_luong(ky_cong):
    tham_so = urlencode({'month': ky_cong.thang, 'year': ky_cong.nam})
    return redirect(reverse('bang_luong:list') + '?' + tham_so)


@login_required
def danh_sach_bang_luong(request):
    if not has_role(request.user, HR, DIRECTOR, MANAGER):
        messages.error(request, 'Bạn không có quyền truy cập chức năng quản lý lương.')
        dich_den = reverse('bang_luong:personal')
        tham_so_ky = urlencode({khoa: request.GET[khoa] for khoa in ['month', 'year'] if request.GET.get(khoa)})
        return redirect(dich_den + ('?' + tham_so_ky if tham_so_ky else ''))
    bieu_mau = BoLocBangLuong(request.user, request.GET)
    ds_dong = phieu_luong_trong_pham_vi(request.user, bieu_mau)
    if has_role(request.user, HR, DIRECTOR):
        for dong in ds_dong:
            dong.approval_error = loi_duyet_luong(dong) if dong.trang_thai == 'pending' else ''
    ky_luong = None
    if bieu_mau.is_valid():
        ky_luong = PayrollPeriod.objects.filter(attendance_period__thang=bieu_mau.cleaned_data['month'],
                                               attendance_period__nam=bieu_mau.cleaned_data['year']).first()
    ngu_canh = {'form': bieu_mau, 'rows': ds_dong, 'period': ky_luong,
                  'has_approved_records': ky_luong.records.filter(trang_thai='approved').exists() if ky_luong else False,
                  'month_label': str(bieu_mau['month'].value()).zfill(2), 'year_label': bieu_mau['year'].value(),
                  'can_manage': has_role(request.user, HR, DIRECTOR), 'director': has_role(request.user, DIRECTOR)}
    return render(request, 'payroll/list.html', ngu_canh)


@login_required
def luong_ca_nhan(request):
    bieu_mau = BoLocPhieuLuong(request.GET)
    dong = None
    if bieu_mau.is_valid():
        dong = phieu_luong_ca_nhan(request.user).filter(ky_luong__attendance_period__thang=bieu_mau.cleaned_data['month'],
            ky_luong__attendance_period__nam=bieu_mau.cleaned_data['year']).first()
    ngu_canh = du_lieu_hien_thi_luong(dong) if dong else {}
    ngu_canh.update({'form': bieu_mau, 'row': dong, 'personal': True,
                    'month_label': str(bieu_mau['month'].value()).zfill(2), 'year_label': bieu_mau['year'].value(),
                    'requires_approval': False})
    return render(request, 'payroll/personal.html', ngu_canh)


@login_required
def chi_tiet_luong(request, pk):
    co_quyen_xem_nhom = has_role(request.user, HR, DIRECTOR, MANAGER)
    truy_van = Luong.objects.select_related('ky_luong__attendance_period').filter(
        nhan_vien__in=visible_employees(request.user)) if co_quyen_xem_nhom else phieu_luong_ca_nhan(request.user)
    dong = get_object_or_404(phieu_luong_du_cong_duyet(truy_van), pk=pk)
    ky_luong = dong.ky_luong.attendance_period
    bieu_mau = BoLocPhieuLuong({'month': ky_luong.thang, 'year': ky_luong.nam})
    ngu_canh = du_lieu_hien_thi_luong(dong)
    ngu_canh.update({'form': bieu_mau, 'personal': not co_quyen_xem_nhom, 'month_label': f'{ky_luong.thang:02}',
                    'year_label': ky_luong.nam, 'requires_approval': False})
    return render(request, 'payroll/detail.html', ngu_canh)


@login_required
@require_POST
def duyet_luong_nhan_vien(request, pk):
    require_role(request.user, DIRECTOR)
    dong = get_object_or_404(Luong.objects.select_related('ky_luong__attendance_period'), pk=pk,
                            nhan_vien__in=visible_employees(request.user))
    try:
        duyet_phieu_luong(request.user, dong.pk)
    except ValidationError as loi:
        messages.error(request, '; '.join(loi.messages))
    else:
        messages.success(request, f'Đã duyệt bảng lương của {dong.ten_nhan_vien}.')
    ky_cong = dong.ky_luong.attendance_period
    return _ve_danh_sach_luong(ky_cong)


@login_required
@require_POST
def doi_trang_thai_ky_luong(request, pk):
    require_role(request.user, HR, DIRECTOR)
    ky_luong = get_object_or_404(PayrollPeriod.objects.select_related('attendance_period'), pk=pk)
    try:
        action = request.POST.get('action')
        if action == 'calculate':
            tinh_bang_luong(request.user, pk, request.POST.get('reason', ''))
        else:
            xu_ly_trang_thai_luong(request.user, pk, action, request.POST.get('reason', ''), request.POST.get('evidence', ''))
    except ValidationError as loi:
        messages.error(request, '; '.join(loi.messages))
    else:
        messages.success(request, 'Đã cập nhật bảng lương.')
    return _ve_danh_sach_luong(ky_luong.attendance_period)


@login_required
@require_POST
def xuat_bang_luong(request, fmt):
    require_role(request.user, HR, DIRECTOR)
    bieu_mau = BoLocBangLuong(request.user, request.POST)
    if not bieu_mau.is_valid():
        return render(request, 'form.html', {'form': bieu_mau, 'title': 'Bộ lọc xuất không hợp lệ'}, status=400)
    try:
        du_lieu = bieu_mau.cleaned_data
        return xuat_du_lieu_luong(request.user, phieu_luong_trong_pham_vi(request.user, bieu_mau), fmt, du_lieu['month'], du_lieu['year'],
                              {'employee': du_lieu['employee'].pk if du_lieu['employee'] else None,
                               'department': du_lieu['department'].pk if du_lieu['department'] else None,
                               'q': du_lieu['q'], 'status': du_lieu['status']})
    except ValidationError as loi:
        messages.error(request, '; '.join(loi.messages))
        cac_gia_tri = {khoa: request.POST[khoa] for khoa in ['month', 'year', 'q', 'status', 'department', 'employee']
                  if request.POST.get(khoa)}
        return redirect(reverse('bang_luong:list') + '?' + urlencode(cac_gia_tri))


@login_required
def thiet_lap_luong(request):
    require_role(request.user, HR, DIRECTOR)
    if request.GET.get('employee'):
        try:
            nhan_vien = get_object_or_404(visible_employees(request.user), pk=int(request.GET['employee']))
        except (ValueError, TypeError):
            raise Http404
        tham_so = urlencode({khoa: request.GET[khoa] for khoa in ['month', 'year'] if request.GET.get(khoa)})
        return redirect(reverse('employee_detail', args=[nhan_vien.pk]) + ('?' + tham_so if tham_so else '') + '#payroll-settings')
    return redirect('employees')


@login_required
def chuyen_den_thiet_lap_nhan_vien(request, kind, pk=None, employee_id=None):
    require_role(request.user, HR, DIRECTOR)
    if kind not in ['tax', 'adjustment']:
        raise Http404
    # URL cũ chỉ chuyển đến thiết lập nhân viên, không tạo đầu vào theo kỳ.
    if pk is not None:
        raise Http404
    employee_id = employee_id or request.GET.get('employee')
    if employee_id is None:
        return redirect('employees')
    try:
        nhan_vien = get_object_or_404(visible_employees(request.user), pk=int(employee_id))
    except (ValueError, TypeError):
        raise Http404
    return redirect('employee_edit', employee_id=nhan_vien.pk)
