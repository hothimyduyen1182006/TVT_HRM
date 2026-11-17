from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .access import (
    GIAM_DOC,
    NHAN_SU,
    TRUONG_PHONG,
    co_vai_tro,
    nhan_vien_duoc_hien_thi as nhan_vien_trong_pham_vi,
)
from .forms import (
    BoLocNhanVien,
    BieuMauHocVan,
    BieuMauNhanVien,
    BieuMauHopDong,
    BieuMauHoSoCaNhan,
    BieuMauThietLapLuong,
)
from .models import HocVan, NhanVien, HopDongLaoDong


def ngu_canh_thiet_lap_luong(request, nhan_vien):
    if not nhan_vien or not (
        nhan_vien.nguoi_dung_id == request.user.pk or co_vai_tro(request.user, NHAN_SU, GIAM_DOC)
    ):
        return {}
    return {
        'shared_salary_settings': nhan_vien.thiet_lap_luong,
        'can_manage_salary': co_vai_tro(request.user, NHAN_SU, GIAM_DOC),
        'salary_form': BieuMauThietLapLuong(nhan_vien),
    }


@login_required
def sua_thiet_lap_luong(request, ma_nhan_vien, loai_thiet_lap, ma_ban_ghi=None):
    if not co_vai_tro(request.user,NHAN_SU,GIAM_DOC):
        return tu_choi_truy_cap(request)
    get_object_or_404(nhan_vien_trong_pham_vi(request.user),pk=ma_nhan_vien)
    if loai_thiet_lap not in ('tax', 'adjustment') or ma_ban_ghi is not None:
        raise Http404
    return redirect('employee_edit', ma_nhan_vien=ma_nhan_vien)


VAI_TRO_QUAN_LY = (NHAN_SU, GIAM_DOC)
VAI_TRO_DANH_SACH = (NHAN_SU, GIAM_DOC, TRUONG_PHONG)


def tu_choi_truy_cap(request):
    return render(request, 'nhan_vien/forbidden.html', status=403)


@login_required
def danh_sach_nhan_vien(request):# Mục đích chính vẫn là: lấy danh sách nhân viên phù hợp rồi hiển thị lên trang.
    # Đã login chưa đủ: cần role được vào danh sách. * bung tuple vai trò thành các đối số.
    #1 kiểm tra quyền
    if not co_vai_tro(request.user, *VAI_TRO_DANH_SACH):
        return tu_choi_truy_cap(request)
    # Giới hạn quyền trước rồi mới lọc; bộ lọc không thể mở rộng dữ liệu ngoài phạm vi này.
    danh_sach = nhan_vien_trong_pham_vi(request.user)

    # Form chịu trách nhiệm nhận lựa chọn, kiểm tra dữ liệu và áp dụng bộ lọc.
    bo_loc = BoLocNhanVien(request.user, request.GET)
    danh_sach = bo_loc.loc_danh_sach(danh_sach)
    return render(request, 'nhan_vien/list.html', {
        'rows': danh_sach.select_related('phong_ban', 'chuc_vu', 'nguoi_dung'),
        'filter_form': bo_loc,
        'filters': bo_loc.data,
        'departments': bo_loc.fields['department'].queryset,
        'positions': bo_loc.fields['position'].queryset,
        'status_choices': NhanVien.EMPLOYMENT_STATUS_CHOICES,
        'can_manage': co_vai_tro(request.user, *VAI_TRO_QUAN_LY),
    })


@login_required
def chi_tiet_nhan_vien(request, ma_nhan_vien):
    if not co_vai_tro(request.user, *VAI_TRO_DANH_SACH):
        return tu_choi_truy_cap(request)
    nhan_vien = get_object_or_404(NhanVien.objects.select_related('nguoi_dung', 'phong_ban', 'chuc_vu'), pk=ma_nhan_vien)
    if not nhan_vien_trong_pham_vi(request.user).filter(pk=nhan_vien.pk).exists():
        return tu_choi_truy_cap(request)
    return render(request, 'nhan_vien/detail.html', {
        'employee': nhan_vien,
        'can_manage': False,
        **ngu_canh_thiet_lap_luong(request, nhan_vien),
    })


@login_required
def ho_so_ca_nhan(request):
    nhan_vien = NhanVien.objects.filter(nguoi_dung=request.user).select_related(
        'nguoi_dung', 'phong_ban', 'chuc_vu').first()
    return render(request, 'nhan_vien/detail.html', {
        'employee': nhan_vien,
        'personal_view': True,
        'can_manage': True,
        **ngu_canh_thiet_lap_luong(request, nhan_vien),
    })


@login_required
def sua_ho_so_ca_nhan(request):
    nhan_vien = get_object_or_404(NhanVien.objects.select_related('nguoi_dung'), nguoi_dung=request.user)
    bieu_mau = BieuMauHoSoCaNhan(request.POST or None, request.FILES or None, instance=nhan_vien)
    if request.method == 'POST' and bieu_mau.is_valid():
        bieu_mau.save()
        messages.success(request, 'Hồ sơ cá nhân đã được cập nhật.')
        return redirect('personal_profile')
    return render(request, 'nhan_vien/personal_profile_form.html', {'form': bieu_mau, 'employee': nhan_vien})


@login_required
def tao_nhan_vien(request):
    if not co_vai_tro(request.user, *VAI_TRO_QUAN_LY):
        return tu_choi_truy_cap(request)
    bieu_mau = BieuMauNhanVien(request.POST or None, request.FILES or None)
    bieu_mau_luong = BieuMauThietLapLuong(data=request.POST if request.method == 'POST' and any(khoa.startswith('salary-') for khoa in request.POST) else None)
    if request.method == 'POST' and bieu_mau.is_valid() and (not bieu_mau_luong.is_bound or bieu_mau_luong.is_valid()):
        nhan_vien = bieu_mau.save()
        if bieu_mau_luong.is_bound:
            from bang_luong.services.can_cu_luong_service import luu_thiet_lap_luong
            luu_thiet_lap_luong(request.user, nhan_vien, bieu_mau_luong.du_lieu_thiet_lap())
        messages.success(request, 'Thêm mới nhân viên thành công.')
        return redirect('employee_detail', ma_nhan_vien=nhan_vien.pk)
    return render(request, 'nhan_vien/employee_form.html', {
        'form': bieu_mau,
        'salary_form': bieu_mau_luong,
        'is_create': True,
    })


@login_required
def sua_nhan_vien(request, ma_nhan_vien):
    if not co_vai_tro(request.user, *VAI_TRO_QUAN_LY):
        return tu_choi_truy_cap(request)
    nhan_vien = get_object_or_404(NhanVien.objects.select_related('nguoi_dung'), pk=ma_nhan_vien)
    du_lieu_co_ban = request.POST or None if request.POST.get('action') != 'save_salary' else None
    bieu_mau = BieuMauNhanVien(du_lieu_co_ban, request.FILES or None, instance=nhan_vien)
    bieu_mau_luong = BieuMauThietLapLuong(nhan_vien, request.POST if request.method == 'POST' and any(khoa.startswith('salary-') for khoa in request.POST) else None)
    if request.method=='POST' and request.POST.get('action')=='save_salary':
        if bieu_mau_luong.is_bound and bieu_mau_luong.is_valid():
            from bang_luong.services.can_cu_luong_service import luu_thiet_lap_luong
            nhan_vien = luu_thiet_lap_luong(request.user, nhan_vien, bieu_mau_luong.du_lieu_thiet_lap())
            messages.success(request,'Đã lưu thiết lập tính lương dùng chung của nhân viên.')
            for loi in nhan_vien.payroll_errors: messages.warning(request,loi)
            return redirect('employee_detail', ma_nhan_vien=nhan_vien.pk)
    elif request.method == 'POST' and bieu_mau.is_valid() and (not bieu_mau_luong.is_bound or bieu_mau_luong.is_valid()):
        bieu_mau.save()
        if bieu_mau_luong.is_bound:
            from bang_luong.services.can_cu_luong_service import luu_thiet_lap_luong
            nhan_vien = luu_thiet_lap_luong(request.user, nhan_vien, bieu_mau_luong.du_lieu_thiet_lap())
        if set(bieu_mau.changed_data) & {'luong_co_ban', 'ma_ho_so', 'ho_va_ten', 'phong_ban'}:
            from bang_luong.models import Luong
            from bang_luong.services.tinh_luong_service import cap_nhat_luong_nhan_vien
            months = Luong.objects.filter(trang_thai=Luong.CHO_DUYET).values_list(
                'tong_hop__nam', 'tong_hop__thang',
            ).distinct()
            for year, month in months:
                error = cap_nhat_luong_nhan_vien(request.user, nhan_vien.pk, year, month)
                if error:
                    messages.warning(request, error)
        messages.success(request, 'Sửa hồ sơ thành công.')
        return redirect('employee_detail', ma_nhan_vien=nhan_vien.pk)
    return render(request, 'nhan_vien/employee_form.html', {
        'form': bieu_mau,
        'salary_form': bieu_mau_luong,
        'employee': nhan_vien,
        'can_manage': True,
    })


def co_the_sua_ho_so(nguoi_dung, nhan_vien):
    return co_vai_tro(nguoi_dung, *VAI_TRO_QUAN_LY) or nhan_vien.nguoi_dung_id == nguoi_dung.pk


def chuyen_den_ho_so(request, nhan_vien):
    if nhan_vien.nguoi_dung_id == request.user.pk:
        return redirect('personal_profile')
    return redirect('employee_detail', ma_nhan_vien=nhan_vien.pk)


def xu_ly_bieu_mau_ho_so(request, ma_nhan_vien, ma_ban_ghi, mo_hinh, lop_bieu_mau, loai, tieu_de):
    nhan_vien = get_object_or_404(NhanVien, pk=ma_nhan_vien)
    if not co_the_sua_ho_so(request.user, nhan_vien):
        return tu_choi_truy_cap(request)
    ban_ghi = get_object_or_404(mo_hinh, pk=ma_ban_ghi, ho_so_ca_nhan=nhan_vien) if ma_ban_ghi else None
    bieu_mau = lop_bieu_mau(request.POST or None, request.FILES or None, instance=ban_ghi)
    if request.method == 'POST' and bieu_mau.is_valid():
        ban_ghi = bieu_mau.save(commit=False)
        ban_ghi.ho_so_ca_nhan = nhan_vien
        ban_ghi.save()
        messages.success(request, f'{tieu_de} đã được lưu.')
        return chuyen_den_ho_so(request, nhan_vien)
    return render(request, 'nhan_vien/record_form.html', {
        'form': bieu_mau,
        'employee': nhan_vien,
        'record': ban_ghi,
        'kind': loai,
        'title': tieu_de,
        'is_edit': ban_ghi is not None,
        'personal_view': nhan_vien.nguoi_dung_id == request.user.pk,
    })


@login_required
def sua_hoc_van(request, ma_nhan_vien, ma_ban_ghi=None):
    return xu_ly_bieu_mau_ho_so(request, ma_nhan_vien, ma_ban_ghi, HocVan, BieuMauHocVan, 'education', 'Thông tin học vấn')


@login_required
def sua_hop_dong_lao_dong(request, ma_nhan_vien, ma_ban_ghi=None):
    return xu_ly_bieu_mau_ho_so(request, ma_nhan_vien, ma_ban_ghi, HopDongLaoDong, BieuMauHopDong, 'contract', 'Thông tin hợp đồng lao động')


@login_required
@require_POST
def xoa_hoc_van(request, ma_nhan_vien, ma_ban_ghi):
    nhan_vien = get_object_or_404(NhanVien, pk=ma_nhan_vien)
    if not co_the_sua_ho_so(request.user, nhan_vien):
        return tu_choi_truy_cap(request)
    ban_ghi = get_object_or_404(HocVan, pk=ma_ban_ghi, ho_so_ca_nhan=nhan_vien)
    if ban_ghi.tep_bang_cap:
        ban_ghi.tep_bang_cap.delete(save=False)
    ban_ghi.delete()
    messages.success(request, 'Đã xóa thông tin học vấn.')
    return chuyen_den_ho_so(request, nhan_vien)


@login_required
@require_POST
def xoa_hop_dong_lao_dong(request, ma_nhan_vien, ma_ban_ghi):
    nhan_vien = get_object_or_404(NhanVien, pk=ma_nhan_vien)
    if not co_the_sua_ho_so(request.user, nhan_vien):
        return tu_choi_truy_cap(request)
    ban_ghi = get_object_or_404(HopDongLaoDong, pk=ma_ban_ghi, ho_so_ca_nhan=nhan_vien)
    if ban_ghi.tep_hop_dong:
        ban_ghi.tep_hop_dong.delete(save=False)
    ban_ghi.delete()
    messages.success(request, 'Đã xóa hợp đồng lao động.')
    return chuyen_den_ho_so(request, nhan_vien)
