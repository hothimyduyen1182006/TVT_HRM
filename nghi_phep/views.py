from datetime import timedelta
from mimetypes import guess_type

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, SuspiciousFileOperation, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe

from bang_cong.services.quy_trinh import cap_nhat_tong_hop
from bang_luong.models import PayrollPeriod
from nhan_vien.access import (
    GIAM_DOC,
    NHAN_SU,
    TRUONG_PHONG,
    co_vai_tro,
    nhan_vien_duoc_hien_thi,
    yeu_cau_vai_tro,
)
from nhan_vien.models import NhanVien, PhongBan

from .forms import (
    CAC_LOAI_TEP_CHO_PHEP,
    DonNghiPhepForm,
    LocDonNghiPhepForm,
    TepMinhChungForm,
)
from .models import SO_NGAY_PHEP_NAM, DonNghiPhep, NgayNghi, tinh_ngay_phep_da_dung


VAI_TRO_DUOC_DUYET = (NHAN_SU, GIAM_DOC, TRUONG_PHONG)


# Trả về danh sách nhân viên người dùng được xem, kèm hồ sơ của chính họ nếu có.
def pham_vi_co_the_xem(nguoi_dung, nhan_vien=None):
    pham_vi = nhan_vien_duoc_hien_thi(nguoi_dung)
    if nhan_vien:
        pham_vi |= NhanVien.objects.filter(pk=nhan_vien.pk)
    return pham_vi


@login_required
def danh_sach_don_nghi(request):
    nhan_vien = NhanVien.objects.filter(nguoi_dung=request.user, dang_hoat_dong=True).first()
    la_nguoi_duyet = co_vai_tro(request.user, *VAI_TRO_DUOC_DUYET)
    pham_vi = nhan_vien_duoc_hien_thi(request.user) if la_nguoi_duyet else NhanVien.objects.none()

    tab_mac_dinh = 'manage' if la_nguoi_duyet else 'mine'
    tab_yeu_cau = request.POST.get('view') if request.method == 'POST' else request.GET.get('view')
    tab_hien_tai = tab_yeu_cau if la_nguoi_duyet and tab_yeu_cau in {'mine', 'manage'} else tab_mac_dinh
    dang_quan_ly = la_nguoi_duyet and tab_hien_tai == 'manage'

    cac_don = DonNghiPhep.objects.select_related('nhan_vien', 'nhan_vien__phong_ban', 'nguoi_duyet')
    if dang_quan_ly:
        cac_don = cac_don.filter(nhan_vien__in=pham_vi)
    elif nhan_vien:
        cac_don = cac_don.filter(nhan_vien=nhan_vien)
    else:
        cac_don = cac_don.none()

    bieu_mau = DonNghiPhepForm(
        data=request.POST or None,
        files=request.FILES or None,
        nhan_vien=nhan_vien,
    )
    if request.method == 'POST':
        if not nhan_vien:
            messages.error(request, 'Tài khoản chưa được liên kết với hồ sơ nhân viên.')
        elif bieu_mau.is_valid():
            don = bieu_mau.save(commit=False)
            don.save()
            messages.success(request, 'Đã gửi đơn nghỉ phép.')
            if la_nguoi_duyet:
                return redirect(f"{reverse('nghi_phep:list')}?view=mine")
            return redirect('nghi_phep:list')

    cac_phong_ban = (
        PhongBan.objects.filter(pk__in=pham_vi.values('phong_ban_id')).distinct()
        if la_nguoi_duyet else PhongBan.objects.none()
    )
    bo_loc = LocDonNghiPhepForm(cac_phong_ban, request.GET)
    if not bo_loc.is_valid():
        cac_don = cac_don.none()
    else:
        dieu_kien = bo_loc.cleaned_data
        if dieu_kien['q']:
            cac_don = cac_don.filter(
                Q(nhan_vien__ho_va_ten__icontains=dieu_kien['q'])
                | Q(nhan_vien__ma_ho_so__icontains=dieu_kien['q'])
            )
        cac_truong_loc = {
            'department': 'nhan_vien__phong_ban_id',
            'status': 'trang_thai',
            'leave_type': 'loai_nghi',
            'start_date': 'ngay_ket_thuc__gte',
            'end_date': 'ngay_bat_dau__lte',
        }
        for ten_truong, truong_model in cac_truong_loc.items():
            if dieu_kien[ten_truong]:
                cac_don = cac_don.filter(**{truong_model: dieu_kien[ten_truong]})

    # Đọc ngày bắt đầu hợp lệ ngay cả khi trường khác trong form có lỗi.
    ngay_chon = None
    if bieu_mau.is_bound:
        bieu_mau.is_valid()
        ngay_chon = bieu_mau.cleaned_data.get('ngay_bat_dau')

    nam_phep = ngay_chon.year if ngay_chon else timezone.localdate().year
    da_dung = tinh_ngay_phep_da_dung(nhan_vien, nam_phep) if nhan_vien else 0

    return render(request, 'nghi_phep/list.html', {
        'requests': cac_don,
        'form': bieu_mau,
        'filters': bo_loc,
        'is_reviewer': la_nguoi_duyet,
        'own_employee': nhan_vien,
        'can_review': la_nguoi_duyet,
        'active_view': tab_hien_tai,
        'manage_view': dang_quan_ly,
        'annual_leave_year': nam_phep,
        'annual_leave_remaining': max(0, SO_NGAY_PHEP_NAM - da_dung),
    })


@login_required
def chi_tiet_don_nghi(request, ma_don):
    ma_nhan_vien_lien_ket = NhanVien.objects.filter(nguoi_dung=request.user).values_list('pk', flat=True).first()
    nhan_vien = NhanVien.objects.filter(nguoi_dung=request.user, dang_hoat_dong=True).first()
    don = get_object_or_404(
        DonNghiPhep.objects.select_related('nhan_vien', 'nhan_vien__phong_ban', 'nguoi_duyet'),
        pk=ma_don,
        nhan_vien__in=pham_vi_co_the_xem(request.user, nhan_vien),
    )
    duoc_duyet = (
        co_vai_tro(request.user, *VAI_TRO_DUOC_DUYET)
        and don.nhan_vien_id != ma_nhan_vien_lien_ket
    )
    tab_quay_lai = request.GET.get('view', 'manage' if duoc_duyet else 'mine')
    if tab_quay_lai not in ('mine', 'manage'):
        tab_quay_lai = 'manage' if duoc_duyet else 'mine'

    try:
        co_tep = bool(don.tep_dinh_kem and don.tep_dinh_kem.storage.exists(don.tep_dinh_kem.name))
    except (OSError, SuspiciousFileOperation):
        co_tep = False

    return render(request, 'nghi_phep/detail.html', {
        'item': don,
        'can_review': duoc_duyet,
        'days_count': don.so_ngay_nghi,
        'back_view': tab_quay_lai,
        'evidence_available': co_tep,
        'can_attach_evidence': bool(
            don.trang_thai == 'cho_duyet'
            and don.nhan_vien_id == ma_nhan_vien_lien_ket
            and not co_tep
        ),
        'can_cancel': (
            don.trang_thai == 'cho_duyet'
            and don.nhan_vien_id == ma_nhan_vien_lien_ket
        ),
    })


@login_required
@require_POST
def huy_don_nghi(request, ma_don):
    nhan_vien = NhanVien.objects.filter(nguoi_dung=request.user, dang_hoat_dong=True).first()
    if not nhan_vien:
        raise PermissionDenied

    with transaction.atomic():
        don = get_object_or_404(
            DonNghiPhep.objects.select_for_update(),
            pk=ma_don,
            nhan_vien=nhan_vien,
        )
        try:
            don.huy()
        except ValidationError as loi:
            messages.error(request, '; '.join(loi.messages))
        else:
            messages.success(request, 'Đã hủy đơn nghỉ phép.')

    return redirect('nghi_phep:detail', ma_don=don.pk)


@login_required
@require_POST
def bo_sung_minh_chung(request, ma_don):
    nhan_vien = NhanVien.objects.filter(nguoi_dung=request.user, dang_hoat_dong=True).first()
    if not nhan_vien:
        raise PermissionDenied
    don = get_object_or_404(
        DonNghiPhep, pk=ma_don, nhan_vien=nhan_vien, trang_thai='cho_duyet',
    )
    if don.tep_dinh_kem and don.tep_dinh_kem.storage.exists(don.tep_dinh_kem.name):
        messages.error(request, 'Đơn này đã có tệp minh chứng.')
        return redirect('nghi_phep:detail', ma_don=don.pk)

    bieu_mau = TepMinhChungForm(request.POST, request.FILES)
    if bieu_mau.is_valid():
        don.tep_dinh_kem = bieu_mau.cleaned_data['tep_dinh_kem']
        don.save(update_fields=['tep_dinh_kem'])
        ten_tep = don.tep_dinh_kem.name.rsplit('/', 1)[-1]
        messages.success(request, f'Đã đính kèm tệp minh chứng "{ten_tep}".')
    else:
        messages.error(request, '; '.join(err for loi in bieu_mau.errors.values() for err in loi))
    return redirect('nghi_phep:detail', ma_don=don.pk)


@never_cache
@login_required
@require_safe
def tai_minh_chung(request, ma_don):
    nhan_vien = NhanVien.objects.filter(nguoi_dung=request.user, dang_hoat_dong=True).first()
    don = get_object_or_404(
        DonNghiPhep,
        pk=ma_don,
        nhan_vien__in=pham_vi_co_the_xem(request.user, nhan_vien),
    )
    if not don.tep_dinh_kem:
        raise Http404
    loai_tep = guess_type(don.tep_dinh_kem.name)[0] or 'application/octet-stream'
    try:
        tep = don.tep_dinh_kem.open('rb')
    except (OSError, SuspiciousFileOperation):
        raise Http404

    phan_hoi = FileResponse(
        tep,
        content_type=loai_tep,
        as_attachment=loai_tep not in CAC_LOAI_TEP_CHO_PHEP,
        filename=don.tep_dinh_kem.name.rsplit('/', 1)[-1],
    )
    phan_hoi['X-Content-Type-Options'] = 'nosniff'
    return phan_hoi


@login_required
@require_POST
def xu_ly_don_nghi(request, ma_don, thao_tac):
    yeu_cau_vai_tro(request.user, *VAI_TRO_DUOC_DUYET)
    don = get_object_or_404(
        DonNghiPhep.objects.select_related('nhan_vien'),
        pk=ma_don,
        nhan_vien__in=nhan_vien_duoc_hien_thi(request.user),
    )
    nhan_vien_dang_dung = NhanVien.objects.filter(nguoi_dung=request.user).only('pk').first()
    if nhan_vien_dang_dung and don.nhan_vien_id == nhan_vien_dang_dung.pk:
        raise PermissionDenied
    if don.trang_thai != 'cho_duyet' or thao_tac not in ('approve', 'reject'):
        messages.error(request, 'Đơn này đã được xử lý hoặc thao tác không hợp lệ.')
        return redirect('nghi_phep:detail', ma_don=don.pk)

    ghi_chu = request.POST.get('ghi_chu_duyet', '').strip()
    if thao_tac == 'reject' and not ghi_chu:
        messages.error(request, 'Vui lòng nhập lý do từ chối.')
        return redirect('nghi_phep:detail', ma_don=don.pk)

    try:
        with transaction.atomic():
            don = DonNghiPhep.objects.select_for_update().get(pk=ma_don)
            if don.trang_thai != 'cho_duyet':
                raise ValidationError('Đơn này đã được xử lý.')
            if thao_tac == 'approve':
                don.full_clean()
                for so_ngay in range(don.so_ngay_nghi):
                    NgayNghi.objects.create(
                        don_nghi_phep=don,
                        ngay=don.ngay_bat_dau + timedelta(days=so_ngay),
                    )
                don.trang_thai = 'da_duyet'
            else:
                don.trang_thai = 'tu_choi'

            don.ghi_chu_duyet = ghi_chu
            don.nguoi_duyet = request.user
            don.ngay_duyet = timezone.now()
            don.save(update_fields=['trang_thai', 'ghi_chu_duyet', 'nguoi_duyet', 'ngay_duyet'])

            if thao_tac == 'approve':
                thang_dau = (don.ngay_bat_dau.year, don.ngay_bat_dau.month)
                thang_cuoi = (don.ngay_ket_thuc.year, don.ngay_ket_thuc.month)
                for ky_cong in PayrollPeriod.objects.filter(
                    nam__gte=don.ngay_bat_dau.year,
                    nam__lte=don.ngay_ket_thuc.year,
                ):
                    if thang_dau <= (ky_cong.nam, ky_cong.thang) <= thang_cuoi:
                        cap_nhat_tong_hop(don.nhan_vien, ky_cong)
    except ValidationError as loi:
        messages.error(request, '; '.join(loi.messages))
    except IntegrityError:
        messages.error(request, 'Một ngày trong đơn đã có dữ liệu nghỉ phép. Vui lòng kiểm tra bảng công.')
    else:
        messages.success(request, 'Đã cập nhật trạng thái đơn nghỉ phép.')
    return redirect('nghi_phep:detail', ma_don=don.pk)
