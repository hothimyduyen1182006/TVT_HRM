from decimal import InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from nhan_vien.access import (
    GIAM_DOC, NHAN_SU, TRUONG_PHONG,
    co_vai_tro,
)

from .forms import BoLocBangLuong, BoLocPhieuLuong
from .models import Luong

from .services.tinh_luong_service import (
    bang_cong_can_tinh_luong,
    co_quyen_ky_luong,
    co_quyen_tinh_va_gui_luong,
    tinh_bang_luong,
    gui_bang_luong_cho_giam_doc,
    duyet_toan_bo_bang_luong,
    them_cac_khoan_tong,
)
from .services.xuat_luong_service import (
    bang_luong_trong_pham_vi,
    co_quyen_xuat_luong,
    phieu_luong_ca_nhan,
    xuat_du_lieu_luong,
)


# Lấy dữ liệu bộ lọc từ URL
def _du_lieu_loc(request):
    hom_nay = timezone.localdate()
    return {
        'thang': request.GET.get('thang') or hom_nay.month,
        'nam': request.GET.get('nam') or hom_nay.year,
        'tu_khoa': request.GET.get('tu_khoa', ''),
        'phong_ban': request.GET.get('phong_ban', ''),
        'trang_thai': request.GET.get('trang_thai', ''),
    }


# Lọc theo nhân viên, phòng ban và trạng thái
def _loc_bang_luong(bang_luong, du_lieu):
    tu_khoa = du_lieu['tu_khoa']
    phong_ban = du_lieu['phong_ban']
    trang_thai = du_lieu['trang_thai']

    if tu_khoa:
        bang_luong = bang_luong.filter(
            tong_hop__nhan_vien__ho_va_ten__icontains=tu_khoa,
        )

    if phong_ban:
        bang_luong = bang_luong.filter(
            tong_hop__nhan_vien__phong_ban=phong_ban,
        )

    if trang_thai:
        bang_luong = bang_luong.filter(trang_thai=trang_thai)

    return bang_luong


# Xem danh sách bảng lương
@login_required
def danh_sach_bang_luong(request):
    if not co_vai_tro(request.user, NHAN_SU, GIAM_DOC, TRUONG_PHONG):
        return redirect('bang_luong:ca_nhan')

    form = BoLocBangLuong(_du_lieu_loc(request))
    form_hop_le = form.is_valid()
    phieu_trong_ky = Luong.objects.none()
    bang_luong = phieu_trong_ky

    if form_hop_le:
        du_lieu = form.cleaned_data
        thang = du_lieu['thang']
        nam = du_lieu['nam']

        phieu_trong_ky = bang_luong_trong_pham_vi(request.user, Luong.objects.all()).filter(
            tong_hop__thang=thang,
            tong_hop__nam=nam,
        ).select_related('tong_hop__nhan_vien__phong_ban', 'tong_thuong')
        bang_luong = _loc_bang_luong(phieu_trong_ky, du_lieu)

    # Kiểm tra quyền thực hiện các chức năng
    co_quyen_tinh_va_gui = co_quyen_tinh_va_gui_luong(request.user)
    co_quyen_ky_theo_vai_tro = co_quyen_ky_luong(request.user)
    co_quyen_xuat = co_quyen_xuat_luong(request.user)
    co_phieu = phieu_trong_ky.exists()
    co_quyen_tinh = (
        form_hop_le and co_quyen_tinh_va_gui
        and bang_cong_can_tinh_luong(nam, thang).exists()
    )
    co_quyen_gui = (
        co_quyen_tinh_va_gui and co_phieu
        and not phieu_trong_ky.exclude(trang_thai='Cho_duyet').exists()
    )
    co_quyen_ky = (
        co_quyen_ky_theo_vai_tro and co_phieu
        and not phieu_trong_ky.exclude(trang_thai='Cho_giam_doc_duyet').exists()
    )

    return render(request, 'bang_luong/list.html', {
        'form': form,
        'bang_luong': bang_luong,
        'co_quyen_tinh': co_quyen_tinh,
        'co_quyen_gui': co_quyen_gui,
        'co_quyen_ky': co_quyen_ky,
        'co_quyen_xuat': co_quyen_xuat,
        'co_quyen_xem_tat_ca': co_vai_tro(request.user, NHAN_SU, GIAM_DOC),
    })


# Xem phiếu lương cá nhân
@login_required
def luong_ca_nhan(request):
    form = BoLocPhieuLuong(_du_lieu_loc(request))
    bang_luong = Luong.objects.none()

    if form.is_valid():
        thang = form.cleaned_data['thang']
        nam = form.cleaned_data['nam']

        bang_luong = phieu_luong_ca_nhan(request.user).filter(
            tong_hop__thang=thang,
            tong_hop__nam=nam,
        )

    return render(request, 'bang_luong/list.html', {
        'form': form,
        'bang_luong': them_cac_khoan_tong(bang_luong),
        'ca_nhan': True,
    })


def _xu_ly_bang_luong_theo_ky(request, thao_tac, thong_bao_thanh_cong):
    """Kiểm tra kỳ lương, thực hiện thao tác và quay về danh sách."""
    form = BoLocPhieuLuong(request.POST)

    if not form.is_valid():
        messages.error(request, 'Tháng và năm không hợp lệ.')
        return redirect('bang_luong:danh_sach')

    thang = form.cleaned_data['thang']
    nam = form.cleaned_data['nam']

    try:
        so_phieu = thao_tac(request.user, nam, thang)
        messages.success(
            request,
            thong_bao_thanh_cong.format(so_phieu=so_phieu, thang=thang, nam=nam),
        )
    except InvalidOperation:
        messages.error(request, 'Không thể xử lý bảng lương vì có số liệu không hợp lệ.')
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))

    url = reverse('bang_luong:danh_sach')
    return redirect(f'{url}?thang={thang}&nam={nam}')


@login_required
@require_POST
def tinh_luong(request):
    return _xu_ly_bang_luong_theo_ky(
        request, tinh_bang_luong,
        'Đã tính {so_phieu} phiếu lương tháng {thang:02}/{nam}.',
    )


@login_required
@require_POST
def gui_bang_luong(request):
    return _xu_ly_bang_luong_theo_ky(
        request, gui_bang_luong_cho_giam_doc,
        'Đã gửi {so_phieu} phiếu lương tháng {thang:02}/{nam} cho Giám đốc.',
    )


@login_required
@require_POST
def ky_duyet_bang_luong(request):
    return _xu_ly_bang_luong_theo_ky(
        request, duyet_toan_bo_bang_luong,
        'Đã duyệt {so_phieu} phiếu lương tháng {thang:02}/{nam}.',
    )


# Xuất bảng lương
@login_required
def xuat_bang_luong(request, fmt):
    if not co_quyen_xuat_luong(request.user):
        raise PermissionDenied('Không có quyền xuất bảng lương.')

    if fmt not in ('csv', 'json', 'txt'):
        raise PermissionDenied('Định dạng tệp không hợp lệ.')
    form = BoLocBangLuong(_du_lieu_loc(request))

    if not form.is_valid():
        messages.error(request, 'Điều kiện lọc không hợp lệ.')
        return redirect('bang_luong:danh_sach')

    du_lieu = form.cleaned_data
    thang = du_lieu['thang']
    nam = du_lieu['nam']
    bang_luong = _loc_bang_luong(Luong.objects.all(), du_lieu)

    try:
        return xuat_du_lieu_luong(
            request.user, bang_luong, fmt, thang, nam,
        )
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))
        return redirect('bang_luong:danh_sach')
