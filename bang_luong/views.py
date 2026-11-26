from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from nhan_vien.access import (
    GIAM_DOC, NHAN_SU, TRUONG_PHONG,
    co_vai_tro, nhan_vien_duoc_hien_thi,
)

from .forms import BoLocBangLuong, BoLocPhieuLuong
from .models import Luong

from .services.tinh_luong_service import (
    tinh_bang_luong,
    gui_bang_luong_cho_giam_doc,
    duyet_toan_bo_bang_luong,
)
from .services.xuat_luong_service import (
    phieu_luong_ca_nhan,
    xuat_du_lieu_luong,
)


# Lấy bảng lương theo phạm vi được phép xem
def _bang_luong_trong_pham_vi(user):
    nhan_vien = nhan_vien_duoc_hien_thi(user)

    return Luong.objects.filter(
        tong_hop__nhan_vien__in=nhan_vien,
        tong_thuong__trang_thai='da_duyet',
    ).select_related(
        'tong_hop__nhan_vien__phong_ban',
        'tong_thuong',
    )


# Tính tổng thu nhập và tổng khấu trừ
def _them_cac_khoan_tong(bang_luong):
    return bang_luong.annotate(
        tong_thu_nhap=(
            F('luong_theo_cong')
            + F('luong_tang_ca')
            + F('phu_cap')
            + F('tong_tien_thuong')
        ),
        tong_khau_tru=(
            F('khau_tru_bhxh')
            + F('thue_tncn')
            + F('khau_tru_khac')
        ),
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

        phieu_trong_ky = _bang_luong_trong_pham_vi(request.user).filter(
            tong_hop__thang=thang,
            tong_hop__nam=nam,
        )
        bang_luong = _loc_bang_luong(phieu_trong_ky, du_lieu)

    # Kiểm tra quyền thực hiện các chức năng
    la_nhan_su = co_vai_tro(request.user, NHAN_SU)
    la_giam_doc = co_vai_tro(request.user, GIAM_DOC)
    co_phieu = phieu_trong_ky.exists()
    co_phieu_khoa = phieu_trong_ky.filter(
        trang_thai__in=['Cho_giam_doc_duyet', 'Da_duyet'],
    ).exists()

    co_quyen_tinh = form_hop_le and la_nhan_su and not co_phieu_khoa
    co_quyen_gui = (
        la_nhan_su and co_phieu
        and not phieu_trong_ky.exclude(trang_thai='Cho_duyet').exists()
    )
    co_quyen_ky = (
        la_giam_doc and co_phieu
        and not phieu_trong_ky.exclude(trang_thai='Cho_giam_doc_duyet').exists()
    )

    return render(request, 'bang_luong/list.html', {
        'form': form,
        'bang_luong': bang_luong,
        'co_quyen_tinh': co_quyen_tinh,
        'co_quyen_gui': co_quyen_gui,
        'co_quyen_ky': co_quyen_ky,
        'co_quyen_xuat': la_nhan_su or la_giam_doc,
        'co_quyen_xem_tat_ca': la_nhan_su or la_giam_doc,
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
        'bang_luong': _them_cac_khoan_tong(bang_luong),
        'ca_nhan': True,
    })


# Xem chi tiết phiếu lương
@login_required
def chi_tiet_luong(request, pk):
    bang_luong = _bang_luong_trong_pham_vi(request.user)
    bang_luong = _them_cac_khoan_tong(bang_luong)
    phieu = get_object_or_404(bang_luong, pk=pk)
    return render(request, 'bang_luong/detail.html', {'phieu': phieu})


# Tính bảng lương
@login_required
@require_POST
def tinh_luong(request):
    form = BoLocPhieuLuong(request.POST)

    if not form.is_valid():
        messages.error(request, 'Tháng và năm không hợp lệ.')
        return redirect('bang_luong:danh_sach')

    thang = form.cleaned_data['thang']
    nam = form.cleaned_data['nam']

    try:
        so_phieu = tinh_bang_luong(request.user, nam, thang)
        messages.success(request, f'Đã tính {so_phieu} phiếu lương tháng {thang:02}/{nam}.')
    except ValidationError as error:
        messages.error(request, '; '.join(error.messages))

    url = reverse('bang_luong:danh_sach')
    return redirect(f'{url}?thang={thang}&nam={nam}')


# Nhân sự gửi bảng lương cho Giám đốc
@login_required
@require_POST
def gui_bang_luong(request):
    form = BoLocPhieuLuong(request.POST)

    if not form.is_valid():
        messages.error(request, 'Tháng và năm không hợp lệ.')
        return redirect('bang_luong:danh_sach')

    thang = form.cleaned_data['thang']
    nam = form.cleaned_data['nam']

    try:
        so_phieu = gui_bang_luong_cho_giam_doc(request.user, nam, thang)
        messages.success(
            request,
            f'Đã gửi {so_phieu} phiếu lương tháng {thang:02}/{nam} cho Giám đốc.',
        )
    except ValidationError as error:
        messages.error(request, '; '.join(error.messages))

    url = reverse('bang_luong:danh_sach')
    return redirect(f'{url}?thang={thang}&nam={nam}')


# Giám đốc ký duyệt bảng lương
@login_required
@require_POST
def ky_duyet_bang_luong(request):
    form = BoLocPhieuLuong(request.POST)

    if not form.is_valid():
        messages.error(request, 'Tháng và năm không hợp lệ.')
        return redirect('bang_luong:danh_sach')

    thang = form.cleaned_data['thang']
    nam = form.cleaned_data['nam']

    try:
        so_phieu = duyet_toan_bo_bang_luong(request.user, nam, thang)
        messages.success(request, f'Đã duyệt {so_phieu} phiếu lương tháng {thang:02}/{nam}.')
    except ValidationError as error:
        messages.error(request, '; '.join(error.messages))

    url = reverse('bang_luong:danh_sach')
    return redirect(f'{url}?thang={thang}&nam={nam}')


# Xuất bảng lương
@login_required
def xuat_bang_luong(request, fmt):
    if not co_vai_tro(request.user, NHAN_SU, GIAM_DOC):
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
