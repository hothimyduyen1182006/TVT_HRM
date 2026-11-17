from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from nhan_vien.access import (
    GIAM_DOC, NHAN_SU, TRUONG_PHONG, co_vai_tro, nhan_vien_duoc_hien_thi,
)
from .forms import BoLocBangLuong, BoLocPhieuLuong
from .models import Luong
from .services.tinh_luong_service import (
    duyet_toan_bo_bang_luong, gui_bang_luong_cho_giam_doc, tinh_bang_luong,
)
from .services.xuat_luong_service import xuat_du_lieu_luong


def _la_quan_ly(user):
    return co_vai_tro(user, NHAN_SU, GIAM_DOC, TRUONG_PHONG)


def _bang_luong_trong_pham_vi(user):
    nhan_vien = nhan_vien_duoc_hien_thi(user)
    return Luong.objects.select_related(
        'tong_hop__nhan_vien__phong_ban', 'tong_thuong',
    ).filter(tong_hop__nhan_vien__in=nhan_vien)


def _loc_bang_luong(queryset, form):
    if not form.is_valid():
        return queryset.none()
    du_lieu = form.cleaned_data
    queryset = queryset.filter(
        tong_hop__thang=du_lieu['thang'], tong_hop__nam=du_lieu['nam'],
    )
    if du_lieu['tu_khoa']:
        queryset = queryset.filter(
            tong_hop__nhan_vien__ho_va_ten__icontains=du_lieu['tu_khoa'],
        )
    if du_lieu['phong_ban']:
        queryset = queryset.filter(
            tong_hop__nhan_vien__phong_ban=du_lieu['phong_ban'],
        )
    if du_lieu['trang_thai']:
        queryset = queryset.filter(trang_thai=du_lieu['trang_thai'])
    return queryset.order_by('tong_hop__nhan_vien__ma_ho_so')


def _bo_loc_mac_dinh(request):
    if request.GET:
        return BoLocBangLuong(request.GET)
    hom_nay = timezone_localdate()
    return BoLocBangLuong({'thang': hom_nay.month, 'nam': hom_nay.year})


@login_required
def danh_sach_bang_luong(request):
    if not _la_quan_ly(request.user):
        return redirect('bang_luong:ca_nhan')
    form = _bo_loc_mac_dinh(request)
    rows = _loc_bang_luong(_bang_luong_trong_pham_vi(request.user), form)
    if form.is_valid():
        du_lieu_ky = form.cleaned_data
        phieu_trong_ky = _bang_luong_trong_pham_vi(request.user).filter(
            tong_hop__nam=du_lieu_ky['nam'], tong_hop__thang=du_lieu_ky['thang'],
        )
    else:
        phieu_trong_ky = Luong.objects.none()
    co_phieu = phieu_trong_ky.exists()
    la_nhan_su = co_vai_tro(request.user, NHAN_SU)
    la_giam_doc = co_vai_tro(request.user, GIAM_DOC)
    co_phieu_khoa = phieu_trong_ky.filter(
        trang_thai__in=[Luong.CHO_GIAM_DOC_DUYET, Luong.DA_DUYET],
    ).exists()
    return render(request, 'bang_luong/list.html', {
        'form': form,
        'bang_luong': rows,
        'co_quyen_tinh': la_nhan_su and not co_phieu_khoa,
        'co_quyen_gui': la_nhan_su and co_phieu and not phieu_trong_ky.exclude(
            trang_thai=Luong.CHO_DUYET,
        ).exists(),
        'co_quyen_ky': la_giam_doc and co_phieu and not phieu_trong_ky.exclude(
            trang_thai=Luong.CHO_GIAM_DOC_DUYET,
        ).exists(),
        'co_quyen_xuat': co_vai_tro(request.user, NHAN_SU, GIAM_DOC),
        'co_quyen_xem_tat_ca': co_vai_tro(request.user, NHAN_SU, GIAM_DOC),
    })


@login_required
def luong_ca_nhan(request):
    if request.GET:
        form = BoLocPhieuLuong(request.GET)
    else:
        hom_nay = timezone_localdate()
        form = BoLocPhieuLuong({'thang': hom_nay.month, 'nam': hom_nay.year})
    rows = Luong.objects.none()
    if hasattr(request.user, 'employee'):
        rows = Luong.objects.select_related('tong_hop', 'tong_thuong').filter(
            tong_hop__nhan_vien=request.user.employee,
        ).order_by('-tong_hop__nam', '-tong_hop__thang')
        if form.is_valid():
            rows = rows.filter(
                tong_hop__thang=form.cleaned_data['thang'],
                tong_hop__nam=form.cleaned_data['nam'],
            )
        else:
            rows = rows.none()
    return render(request, 'bang_luong/list.html', {
        'form': form, 'bang_luong': rows, 'ca_nhan': True,
    })


def timezone_localdate():
    from django.utils import timezone
    return timezone.localdate()


@login_required
def chi_tiet_luong(request, pk):
    phieu = get_object_or_404(
        Luong.objects.select_related('tong_hop__nhan_vien__phong_ban', 'tong_thuong'),
        pk=pk,
    )
    if not nhan_vien_duoc_hien_thi(request.user).filter(
        pk=phieu.tong_hop.nhan_vien_id,
    ).exists():
        raise PermissionDenied('Không có quyền truy cập bảng lương này.')
    return render(request, 'bang_luong/detail.html', {
        'phieu': phieu, 'tong_thu_nhap': phieu.tong_thu_nhap,
    })


@login_required
@require_POST
def tinh_luong(request):
    if not co_vai_tro(request.user, NHAN_SU):
        raise PermissionDenied('Chỉ Quản lý nhân sự được tính lương.')
    form = BoLocPhieuLuong(request.POST)
    if not form.is_valid():
        messages.error(request, 'Vui lòng chọn tháng và năm hợp lệ để tính lương.')
        return redirect('bang_luong:danh_sach')

    thang = form.cleaned_data['thang']
    nam = form.cleaned_data['nam']
    try:
        so_phieu = tinh_bang_luong(request.user, nam, thang)
    except ValidationError as error:
        messages.error(request, '; '.join(error.messages))
    else:
        messages.success(request, f'Đã tính và lưu {so_phieu} phiếu lương tháng {thang:02}/{nam}.')
    return redirect(f'{reverse("bang_luong:danh_sach")}?thang={thang}&nam={nam}')


def _xu_ly_duyet_theo_ky(request, xu_ly, thong_bao):
    form = BoLocPhieuLuong(request.POST)
    if not form.is_valid():
        messages.error(request, 'Vui lòng chọn tháng và năm hợp lệ.')
        return redirect('bang_luong:danh_sach')
    thang = form.cleaned_data['thang']
    nam = form.cleaned_data['nam']
    try:
        so_phieu = xu_ly(request.user, nam, thang)
    except ValidationError as error:
        messages.error(request, '; '.join(error.messages))
    else:
        messages.success(request, thong_bao.format(count=so_phieu, month=thang, year=nam))
    return redirect(f'{reverse("bang_luong:danh_sach")}?thang={thang}&nam={nam}')


@login_required
@require_POST
def gui_bang_luong(request):
    return _xu_ly_duyet_theo_ky(
        request, gui_bang_luong_cho_giam_doc,
        'Đã gửi {count} phiếu lương tháng {month:02d}/{year} cho Giám đốc ký.',
    )


@login_required
@require_POST
def ky_duyet_bang_luong(request):
    return _xu_ly_duyet_theo_ky(
        request, duyet_toan_bo_bang_luong,
        'Giám đốc đã ký duyệt {count} phiếu lương tháng {month:02d}/{year}.',
    )


@login_required
def xuat_bang_luong(request, fmt):
    if not co_vai_tro(request.user, NHAN_SU, GIAM_DOC):
        raise PermissionDenied('Không có quyền xuất bảng lương.')
    if fmt not in ('csv', 'json', 'txt'):
        raise PermissionDenied('Định dạng tệp không hợp lệ.')
    form = _bo_loc_mac_dinh(request)
    rows = _loc_bang_luong(_bang_luong_trong_pham_vi(request.user), form)
    if not form.is_valid():
        messages.info(request, 'Vui lòng chọn tháng và năm hợp lệ trước khi xuất.')
        return redirect('bang_luong:danh_sach')
    try:
        return xuat_du_lieu_luong(
            request.user, rows, fmt,
            form.cleaned_data['thang'], form.cleaned_data['nam'],
        )
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))
        return redirect('bang_luong:danh_sach')
