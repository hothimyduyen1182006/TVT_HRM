"""Hiển thị trang chấm công và xử lý thao tác vào ca, kết thúc ca."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from nhan_vien.models import NhanVien

from .models import ChamCong
from .services.cham_cong import ghi_nhan_cham_cong, xem_lich_cham_cong
from .services.quy_trinh import ky_cong_da_khoa


@login_required
@require_http_methods(['GET', 'POST'])
def cham_cong_hom_nay(request):
    nhan_vien = NhanVien.objects.filter(
        nguoi_dung=request.user,
        dang_hoat_dong=True,
    ).first()
    if not nhan_vien:
        raise PermissionDenied('Tài khoản chưa liên kết với nhân viên đang làm việc.')

    hien_tai = timezone.localtime().replace(microsecond=0)
    hom_nay = hien_tai.date()

    if request.method == 'POST':
        thao_tac = request.POST.get('action')
        try:
            ban_ghi = ghi_nhan_cham_cong(
                request.user,
                thao_tac,
            )
            # Lưu để GET sau redirect có thể hiện thao tác vừa thành công.
            request.session['clock_success'] = {
                'record': ban_ghi.pk,
                'action': thao_tac,
            }
        except ValidationError as loi:
            messages.error(request, ' '.join(loi.messages))
        return redirect('bang_cong:cham-cong')

    ban_ghi = ChamCong.objects.filter(nhan_vien=nhan_vien, ngay=hom_nay).first()
    ke_hoach = xem_lich_cham_cong(hom_nay)
    ky_cong = ke_hoach['ky_cong']
    lich_ngay = ke_hoach['lich_ngay']

    da_khoa = ky_cong_da_khoa(ky_cong, nhan_vien.pk, hom_nay) if ky_cong else False
    duoc_cham_cong = bool(
        not ke_hoach['loi']
        and not da_khoa
        and lich_ngay
        and lich_ngay.loai_ngay == 'work'
        and nhan_vien.ngay_vao_lam <= hom_nay
    )
    dang_trong_ca = bool(ban_ghi and ban_ghi.gio_vao and not ban_ghi.gio_ra)
    trang_thai_trang = (
        'da_hoan_tat' if ban_ghi and ban_ghi.gio_ra
        else 'dang_trong_ca' if dang_trong_ca
        else 'chua_vao_ca'
    )

    thao_tac_vua_xong = request.session.pop('clock_success', {})
    if not ban_ghi or thao_tac_vua_xong.get('record') != ban_ghi.pk:
        thao_tac_vua_xong = {}

    return render(request, 'bang_cong/checkin.html', {
        'nhan_vien': nhan_vien,
        'ban_ghi_hom_nay': ban_ghi,
        'ky_cong': ky_cong,
        'hom_nay': hom_nay,
        'thao_tac_thanh_cong': thao_tac_vua_xong.get('action'),
        'trang_thai_trang': trang_thai_trang,
        'co_the_vao_ca': duoc_cham_cong and ban_ghi is None,
        'co_the_ket_thuc_ca': duoc_cham_cong and dang_trong_ca,
        'da_khoa': da_khoa,
        'loi_lich': ke_hoach['loi'],
    })
