from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
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
def danh_sach_nhan_vien(request):
    if not co_vai_tro(request.user, *VAI_TRO_DANH_SACH):
        return tu_choi_truy_cap(request)
    danh_sach = nhan_vien_trong_pham_vi(request.user)
    bo_loc = BoLocNhanVien(request.GET)
    if bo_loc.is_valid():
        ngay_chon = bo_loc.cleaned_data['hoat_dong_den_ngay']
        if ngay_chon:
            danh_sach = danh_sach.filter(dang_hoat_dong=True, ngay_vao_lam__lte=ngay_chon)
        gioi_tinh = bo_loc.cleaned_data['gioi_tinh']
        if gioi_tinh == 'unknown':
            danh_sach = danh_sach.exclude(gioi_tinh__in=['Nam', 'Nữ'])
        elif gioi_tinh:
            danh_sach = danh_sach.filter(gioi_tinh=gioi_tinh)
    else:
        danh_sach = danh_sach.none()
    bo_loc_du_lieu = {
        'q': request.GET.get('q', '').strip()[:100],
        'department': request.GET.get('department', '').strip(),
        'position': request.GET.get('position', '').strip(),
        'status': request.GET.get('status', '').strip(),
        'hire_from': request.GET.get('hire_from', '').strip(),
        'hire_to': request.GET.get('hire_to', '').strip(),
    }
    if bo_loc_du_lieu['q']:
        danh_sach = danh_sach.filter(
            Q(ma_ho_so__icontains=bo_loc_du_lieu['q'])
            | Q(ho_va_ten__icontains=bo_loc_du_lieu['q'])
            | Q(nguoi_dung__username__icontains=bo_loc_du_lieu['q'])
        )
    if bo_loc_du_lieu['department'].isdigit():
        danh_sach = danh_sach.filter(phong_ban_id=bo_loc_du_lieu['department'])
    if bo_loc_du_lieu['position'].isdigit():
        danh_sach = danh_sach.filter(chuc_vu_id=bo_loc_du_lieu['position'])
    if bo_loc_du_lieu['status'] in dict(NhanVien.EMPLOYMENT_STATUS_CHOICES):
        danh_sach = danh_sach.filter(trang_thai_nv=bo_loc_du_lieu['status'])
    ngay_vao_tu = parse_date(bo_loc_du_lieu['hire_from']) if bo_loc_du_lieu['hire_from'] else None
    ngay_vao_den = parse_date(bo_loc_du_lieu['hire_to']) if bo_loc_du_lieu['hire_to'] else None
    if ngay_vao_tu:
        danh_sach = danh_sach.filter(ngay_vao_lam__gte=ngay_vao_tu)
    if ngay_vao_den:
        danh_sach = danh_sach.filter(ngay_vao_lam__lte=ngay_vao_den)

    phong_ban = danh_sach.model.phong_ban.field.remote_field.model.objects.all()
    if co_vai_tro(request.user, TRUONG_PHONG) and not co_vai_tro(request.user, NHAN_SU, GIAM_DOC):
        phong_ban = phong_ban.filter(truong_phong__nguoi_dung=request.user)
    chuc_vu = danh_sach.model.chuc_vu.field.remote_field.model.objects.select_related('phong_ban')
    chuc_vu = chuc_vu.filter(phong_ban__in=phong_ban)
    return render(request, 'nhan_vien/list.html', {
        'dashboard_filter': bo_loc,
        'rows': danh_sach.select_related('phong_ban', 'chuc_vu', 'nguoi_dung'),
        'filters': bo_loc_du_lieu,
        'departments': phong_ban.distinct(),
        'positions': chuc_vu,
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
            from bang_luong.services.quy_trinh import luu_thiet_lap_luong
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
            from bang_luong.services.quy_trinh import luu_thiet_lap_luong
            nhan_vien = luu_thiet_lap_luong(request.user, nhan_vien, bieu_mau_luong.du_lieu_thiet_lap())
            messages.success(request,'Đã lưu thiết lập tính lương dùng chung của nhân viên.')
            for loi in nhan_vien.payroll_errors: messages.warning(request,loi)
            return redirect('employee_detail', ma_nhan_vien=nhan_vien.pk)
    elif request.method == 'POST' and bieu_mau.is_valid() and (not bieu_mau_luong.is_bound or bieu_mau_luong.is_valid()):
        bieu_mau.save()
        if bieu_mau_luong.is_bound:
            from bang_luong.services.quy_trinh import luu_thiet_lap_luong
            nhan_vien = luu_thiet_lap_luong(request.user, nhan_vien, bieu_mau_luong.du_lieu_thiet_lap())
        if set(bieu_mau.changed_data) & {'luong_co_ban', 'ma_ho_so', 'ho_va_ten', 'phong_ban'}:
            from bang_luong.models import PayrollPeriod
            from bang_luong.services.tinh_toan import cap_nhat_luong_nhan_vien
            periods = PayrollPeriod.objects.filter(status='pending').select_related().order_by('pk')
            for period in periods:
                attendance = period.attendance_period
                error = cap_nhat_luong_nhan_vien(request.user, employee.pk, attendance.nam, attendance.thang)
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
