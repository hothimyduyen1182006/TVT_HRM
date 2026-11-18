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

from bang_cong.services.tong_hop_service import cap_nhat_tong_hop
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
    # Lấy hồ sơ nhân viên của tài khoản hiện tại để tạo và xem đơn cá nhân.
    ho_so_cua_toi = NhanVien.objects.filter(
        nguoi_dung=request.user,
        dang_hoat_dong=True,
    ).first()

    # Người duyệt có thêm phạm vi xem đơn của nhân viên thuộc quyền.
    la_nguoi_duyet = co_vai_tro(request.user, *VAI_TRO_DUOC_DUYET)
    nhan_vien_duoc_quan_ly = (
        nhan_vien_duoc_hien_thi(request.user)
        if la_nguoi_duyet else NhanVien.objects.none()
    )

    if la_nguoi_duyet:
        tab_hien_tai = request.GET.get('view') or request.POST.get('view') or 'manage'
        if tab_hien_tai not in ['mine', 'manage']:
            tab_hien_tai = 'manage'
    else:
        tab_hien_tai = 'mine'

    dang_quan_ly = la_nguoi_duyet and tab_hien_tai == 'manage'

    # Chọn danh sách đơn theo tab đang mở.
    cac_don = DonNghiPhep.objects.select_related('nhan_vien', 'nhan_vien__phong_ban', 'nguoi_duyet')
    if dang_quan_ly:
        cac_don = cac_don.filter(nhan_vien__in=nhan_vien_duoc_quan_ly)
    elif ho_so_cua_toi:
        cac_don = cac_don.filter(nhan_vien=ho_so_cua_toi)
    else:
        cac_don = cac_don.none()

    bieu_mau = DonNghiPhepForm(
        data=request.POST if request.method == 'POST' else None,
        files=request.FILES if request.method == 'POST' else None,
        nhan_vien=ho_so_cua_toi,
    )
    if request.method == 'POST':
        bieu_mau_hop_le = bieu_mau.is_valid()
        if not ho_so_cua_toi:
            messages.error(request, 'Tài khoản chưa được liên kết với hồ sơ nhân viên.')
        elif bieu_mau_hop_le:
            don = bieu_mau.save(commit=False)
            don.save()
            messages.success(request, 'Đã gửi đơn nghỉ phép.')
            return redirect(f"{reverse('nghi_phep:list')}?view=mine")

    la_quan_ly_nhan_su = co_vai_tro(request.user, NHAN_SU, GIAM_DOC)
    la_truong_phong = co_vai_tro(request.user, TRUONG_PHONG)
    if la_quan_ly_nhan_su:
        cac_phong_ban = PhongBan.objects.all()
    elif la_truong_phong:
        cac_phong_ban = PhongBan.objects.filter(pk=ho_so_cua_toi.phong_ban_id)
    else:
        cac_phong_ban = PhongBan.objects.none()
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

    # Dùng ngày hợp lệ trong lần kiểm tra form ở trên để chọn năm tính phép.
    ngay_chon = bieu_mau.cleaned_data.get('ngay_bat_dau') if bieu_mau.is_bound else None
    nam_phep = ngay_chon.year if ngay_chon else timezone.localdate().year
    da_dung = tinh_ngay_phep_da_dung(ho_so_cua_toi, nam_phep) if ho_so_cua_toi else 0

    return render(request, 'nghi_phep/list.html', {
        'cac_don': cac_don,
        'bieu_mau': bieu_mau,
        'bo_loc': bo_loc,
        'la_nguoi_duyet': la_nguoi_duyet,
        'ho_so_cua_toi': ho_so_cua_toi,
        'tab_hien_tai': tab_hien_tai,
        'dang_quan_ly': dang_quan_ly,
        'nam_phep': nam_phep,
        'so_ngay_phep_con_lai': max(0, SO_NGAY_PHEP_NAM - da_dung),
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
        'don': don,
        'duoc_duyet': duoc_duyet,
        'so_ngay_nghi': don.so_ngay_nghi,
        'tab_quay_lai': tab_quay_lai,
        'co_tep_minh_chung': co_tep,
        'duoc_huy_don': (
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
                nam, thang = don.ngay_bat_dau.year, don.ngay_bat_dau.month
                while (nam, thang) <= (don.ngay_ket_thuc.year, don.ngay_ket_thuc.month):
                    cap_nhat_tong_hop(don.nhan_vien, nam, thang)
                    if thang == 12:
                        nam, thang = nam + 1, 1
                    else:
                        thang += 1
    except ValidationError as loi:
        messages.error(request, '; '.join(loi.messages))
    except IntegrityError:
        messages.error(request, 'Một ngày trong đơn đã có dữ liệu nghỉ phép. Vui lòng kiểm tra bảng công.')
    else:
        messages.success(request, 'Đã cập nhật trạng thái đơn nghỉ phép.')
    return redirect('nghi_phep:detail', ma_don=don.pk)
