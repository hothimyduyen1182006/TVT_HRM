"""Kiểm tra lịch và ghi nhận giờ vào ca, kết thúc ca."""

import calendar

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from bang_cong.models import ChamCong
from bang_cong.services.quy_trinh import cap_nhat_tong_hop, ky_cong_da_khoa
from bang_cong.services.tinh_toan import lich_thang, tinh_cong_ngay, tinh_phut_di_tre
from bang_cong.thang_lich import thang_lich
from nhan_vien.models import NhanVien


def kiem_tra_lich_lam_viec(ky_cong):
    """Trả về lịch tháng sau khi kiểm tra giờ ca và từng ngày."""
    if not (
        ky_cong.gio_bat_dau < ky_cong.bat_dau_nghi_trua
        < ky_cong.ket_thuc_nghi_trua < ky_cong.gio_ket_thuc
        and ky_cong.gio_chuan > 0
    ):
        raise ValidationError('Thứ tự ca làm hoặc giờ chuẩn không hợp lệ.')

    cac_ngay = list(lich_thang(ky_cong.nam, ky_cong.thang, ky_cong).values())
    so_ngay_trong_thang = calendar.monthrange(ky_cong.nam, ky_cong.thang)[1]
    if len(cac_ngay) != so_ngay_trong_thang:
        raise ValidationError('Chưa cấu hình lịch làm việc cho năm này.')

    for lich_ngay in cac_ngay:
        if (
            lich_ngay.loai_ngay not in ('work', 'rest', 'holiday')
            or not 0 <= lich_ngay.cong_chuan <= 1
            or (lich_ngay.loai_ngay != 'work' and lich_ngay.cong_chuan != 0)
        ):
            raise ValidationError('Lịch áp dụng không hợp lệ.')
    return cac_ngay


def xem_lich_cham_cong(ngay):
    """Đọc lịch ngày; thao tác này không tạo kỳ hoặc ghi dữ liệu."""
    ky_cong = thang_lich(ngay.year, ngay.month)
    ke_hoach = {'ky_cong': ky_cong, 'lich_ngay': None, 'loi': ''}

    try:
        cac_ngay = kiem_tra_lich_lam_viec(ky_cong)
    except ValidationError as loi:
        ke_hoach['loi'] = ' '.join(loi.messages)
        return ke_hoach

    ke_hoach['lich_ngay'] = next(
        lich_ngay for lich_ngay in cac_ngay if lich_ngay.ngay == ngay
    )
    return ke_hoach


def dam_bao_lich_cham_cong(ngay):
    """Trả về kỳ và lịch ngày hợp lệ, hoặc báo lỗi cấu hình lịch."""
    ke_hoach = xem_lich_cham_cong(ngay)
    if ke_hoach['loi']:
        raise ValidationError(ke_hoach['loi'])
    return ke_hoach['ky_cong'], ke_hoach['lich_ngay']


@transaction.atomic
def ghi_nhan_cham_cong(nguoi_dung, thao_tac):
    """Ghi nhận thao tác vào ca hoặc kết thúc ca của nhân viên đang đăng nhập."""
    if not nguoi_dung.is_authenticated:
        raise PermissionDenied('Cần đăng nhập trước khi chấm công.')
    if thao_tac not in ('in', 'out'):
        raise ValidationError('Thao tác không hợp lệ.')

    hien_tai = timezone.localtime().replace(microsecond=0)
    hom_nay = hien_tai.date()
    gio_hien_tai = hien_tai.time()

    nhan_vien = (
        NhanVien.objects.select_for_update()
        .filter(nguoi_dung=nguoi_dung, dang_hoat_dong=True)
        .first()
    )
    if not nhan_vien:
        raise PermissionDenied('Tài khoản chưa liên kết với nhân viên đang làm việc.')

    ky_cong, lich_ngay = dam_bao_lich_cham_cong(hom_nay)
    if ky_cong_da_khoa(ky_cong, nhan_vien.pk, hom_nay):
        raise ValidationError('Bảng công đã duyệt, không thể chấm công thêm.')
    if lich_ngay.loai_ngay != 'work':
        raise ValidationError('Hôm nay chưa có lịch làm việc thông thường được cấu hình.')

    ban_ghi = (
        ChamCong.objects.select_for_update()
        .filter(nhan_vien=nhan_vien, ngay=hom_nay)
        .first()
    )

    if thao_tac == 'in':
        if ban_ghi:
            raise ValidationError('Hôm nay đã có bản ghi chấm công. Không thể vào ca lại.')

        ban_ghi = ChamCong(
            nhan_vien=nhan_vien,
            ngay=hom_nay,
            gio_vao=gio_hien_tai,
            so_phut_tre=tinh_phut_di_tre(hom_nay, gio_hien_tai, ky_cong),
            trang_thai='incomplete',
        )
        ban_ghi.full_clean()
    else:
        if not ban_ghi or not ban_ghi.gio_vao:
            raise ValidationError('Bạn cần vào ca trước.')
        if ban_ghi.gio_ra or ban_ghi.trang_thai != 'incomplete':
            raise ValidationError('Bản ghi đã kết thúc hoặc cần nhân sự kiểm tra.')

        ban_ghi.nhan_vien = nhan_vien
        ban_ghi.gio_ra = gio_hien_tai
        ban_ghi.trang_thai = 'present'
        tinh_cong_ngay(ban_ghi, ky_cong)

    ban_ghi.save()
    cap_nhat_tong_hop(nhan_vien, ky_cong)
    return ban_ghi
