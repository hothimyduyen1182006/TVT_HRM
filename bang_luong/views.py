"""Xử lý request Bảng lương; tách truy vấn hiển thị khỏi thao tác ghi dữ liệu."""
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from nhan_vien.access import nhan_vien_duoc_hien_thi, co_vai_tro, yeu_cau_vai_tro, NHAN_SU, GIAM_DOC, TRUONG_PHONG
from .models import Luong
from bang_cong.thang_lich import thang_lich, thang_tu_ma
from .forms import BoLocBangLuong, BoLocPhieuLuong
from .services.tinh_toan import tinh_bang_luong
from .services.quy_trinh import xu_ly_trang_thai_luong, gui_bang_luong
from .services.hien_thi import (
    xuat_du_lieu_luong, du_lieu_hien_thi_luong, phieu_luong_du_cong_duyet,
    phieu_luong_trong_pham_vi, phieu_luong_ca_nhan,
)


def _ve_danh_sach_luong(ky_cong):
    tham_so = urlencode({'month': ky_cong.thang, 'year': ky_cong.nam})
    return redirect(reverse('bang_luong:list') + '?' + tham_so)


@login_required
def danh_sach_bang_luong(request):
    if not co_vai_tro(request.user, NHAN_SU, GIAM_DOC, TRUONG_PHONG):
        messages.error(request, 'Bạn không có quyền truy cập chức năng quản lý lương.')
        dich_den = reverse('bang_luong:personal')
        tham_so_ky = urlencode({khoa: request.GET[khoa] for khoa in ['month', 'year'] if request.GET.get(khoa)})
        return redirect(dich_den + ('?' + tham_so_ky if tham_so_ky else ''))
    bieu_mau = BoLocBangLuong(request.user, request.GET)
    ds_dong = phieu_luong_trong_pham_vi(request.user, bieu_mau)
    ky_luong = None
    if bieu_mau.is_valid():
        ky_luong = thang_lich(bieu_mau.cleaned_data['year'], bieu_mau.cleaned_data['month'])
    ngu_canh = {'form': bieu_mau, 'rows': ds_dong, 'period': ky_luong,
                  'attendance_approved': ky_luong.trang_thai == 'approved' if ky_luong else False,
                  'month_label': str(bieu_mau['thang'].value()).zfill(2), 'year_label': bieu_mau['nam'].value(),
                  'can_manage': co_vai_tro(request.user, NHAN_SU, GIAM_DOC),
                  'hr': co_vai_tro(request.user, NHAN_SU), 'director': co_vai_tro(request.user, GIAM_DOC)}
    return render(request, 'bang_luong/list.html', ngu_canh)


@login_required
def luong_ca_nhan(request):
    bieu_mau = BoLocPhieuLuong(request.GET)
    dong = None
    if bieu_mau.is_valid():
        dong = phieu_luong_ca_nhan(request.user).filter(
            tong_hop__thang=bieu_mau.cleaned_data['month'],
            tong_hop__nam=bieu_mau.cleaned_data['year']).first()
    ngu_canh = du_lieu_hien_thi_luong(dong) if dong else {}
    ngu_canh.update({'form': bieu_mau, 'row': dong, 'personal': True,
                    'month_label': str(bieu_mau['month'].value()).zfill(2), 'year_label': bieu_mau['year'].value(),
                    'requires_approval': False})
    return render(request, 'bang_luong/personal.html', ngu_canh)


@login_required
def chi_tiet_luong(request, pk):
    co_quyen_xem_nhom = co_vai_tro(request.user, NHAN_SU, GIAM_DOC, TRUONG_PHONG)
    truy_van = Luong.objects.select_related('tong_hop', 'tong_hop__nhan_vien').filter(
        tong_hop__nhan_vien__in=nhan_vien_duoc_hien_thi(request.user)) if co_quyen_xem_nhom else phieu_luong_ca_nhan(request.user)
    dong = get_object_or_404(phieu_luong_du_cong_duyet(truy_van), pk=pk)
    ky_luong = thang_lich(dong.tong_hop.nam, dong.tong_hop.thang)
    bieu_mau = BoLocPhieuLuong({'month': ky_luong.thang, 'year': ky_luong.nam})
    ngu_canh = du_lieu_hien_thi_luong(dong)
    ngu_canh.update({'form': bieu_mau, 'personal': not co_quyen_xem_nhom, 'month_label': f'{ky_luong.thang:02}',
                    'year_label': ky_luong.nam, 'requires_approval': False})
    return render(request, 'bang_luong/detail.html', ngu_canh)


@login_required
@require_POST
def doi_trang_thai_ky_luong(request, pk):
    yeu_cau_vai_tro(request.user, NHAN_SU, GIAM_DOC)
    ky_luong = thang_tu_ma(pk)
    action = request.POST.get('action')
    try:
        if action == 'calculate':
            tinh_bang_luong(request.user, pk, request.POST.get('reason', ''))
        elif action == 'submit':
            gui_bang_luong(request.user, pk)
        else:
            xu_ly_trang_thai_luong(request.user, pk, action, request.POST.get('reason', ''), request.POST.get('evidence', ''))
    except ValidationError as loi:
        messages.error(request, '; '.join(loi.messages))
    else:
        messages.success(request, {
            'submit': 'Đã gửi toàn bộ bảng lương cho Giám đốc ký duyệt.',
            'approve': 'Giám đốc đã ký duyệt toàn bộ bảng lương trong kỳ.',
            'paid': 'Đã xác nhận chi trả bảng lương.',
            'reopen': 'Đã mở lại kỳ lương để kiểm tra và điều chỉnh.',
        }.get(action, 'Đã cập nhật bảng lương.'))
    return _ve_danh_sach_luong(ky_luong)


@login_required
@require_POST
def xuat_bang_luong(request, fmt):
    yeu_cau_vai_tro(request.user, NHAN_SU, GIAM_DOC)
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
    yeu_cau_vai_tro(request.user, NHAN_SU, GIAM_DOC)
    if request.GET.get('employee'):
        try:
            nhan_vien = get_object_or_404(nhan_vien_duoc_hien_thi(request.user), pk=int(request.GET['employee']))
        except (ValueError, TypeError):
            raise Http404
        tham_so = urlencode({khoa: request.GET[khoa] for khoa in ['month', 'year'] if request.GET.get(khoa)})
        return redirect(reverse('employee_detail', args=[nhan_vien.pk]) + ('?' + tham_so if tham_so else '') + '#payroll-settings')
    return redirect('employees')


@login_required
def chuyen_den_thiet_lap_nhan_vien(request, kind, pk=None, employee_id=None):
    yeu_cau_vai_tro(request.user, NHAN_SU, GIAM_DOC)
    if kind not in ['tax', 'adjustment']:
        raise Http404
    # URL cũ chỉ chuyển đến thiết lập nhân viên, không tạo đầu vào theo kỳ.
    if pk is not None:
        raise Http404
    employee_id = employee_id or request.GET.get('employee')
    if employee_id is None:
        return redirect('employees')
    try:
        nhan_vien = get_object_or_404(nhan_vien_duoc_hien_thi(request.user), pk=int(employee_id))
    except (ValueError, TypeError):
        raise Http404
    return redirect('employee_edit', ma_nhan_vien=nhan_vien.pk)
