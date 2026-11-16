"""Kiểm tra, kế thừa lịch làm việc và ghi nhận check-in/check-out."""

import calendar
from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from nhan_vien.models import NhanVien
from bang_cong.models import ChamCong
from bang_cong.thang_lich import thang_lich
from .quy_trinh import ky_cong_da_khoa, cap_nhat_tong_hop
from .tinh_toan import tinh_cong_ngay, lich_thang


def kiem_tra_lich_lam_viec(ky_cong):
    """Kiểm tra ca và lịch từ cấu hình hoặc căn cứ lịch sử."""
    if not ky_cong.gio_bat_dau < ky_cong.bat_dau_nghi_trua < ky_cong.ket_thuc_nghi_trua < ky_cong.gio_ket_thuc or ky_cong.gio_chuan <= 0:
        raise ValidationError('Thứ tự ca làm hoặc giờ chuẩn không hợp lệ.')
    ds_ngay = list(lich_thang(ky_cong.nam, ky_cong.thang, ky_cong).values())
    if len(ds_ngay) != calendar.monthrange(ky_cong.nam, ky_cong.thang)[1]:
        raise ValidationError('Chưa cấu hình lịch làm việc cho năm này.')
    for ngay in ds_ngay:
        if (ngay.loai_ngay not in ('work', 'rest', 'holiday')
                or not 0 <= ngay.cong_chuan <= 1
                or (ngay.loai_ngay != 'work' and ngay.cong_chuan != 0)):
            raise ValidationError('Lịch áp dụng không hợp lệ.')
    return ds_ngay


def xem_lich_cham_cong(ngay):
    """GET chỉ đọc lịch, không mở kỳ hoặc ghi dữ liệu."""
    ky_cong = thang_lich(ngay.year, ngay.month)
    ke_hoach = {'period': ky_cong, 'day': None, 'source': None, 'weekly': {}, 'error': ''}
    try:
        ds_ngay = kiem_tra_lich_lam_viec(ky_cong)
    except ValidationError as loi:
        ke_hoach['error'] = ' '.join(loi.messages)
        return ke_hoach
    ke_hoach.update(period=ky_cong, day=next(lich for lich in ds_ngay if lich.ngay == ngay))
    return ke_hoach


@transaction.atomic
def dam_bao_lich_cham_cong(ngay, nguoi_thuc_hien):
    ke_hoach = xem_lich_cham_cong(ngay)
    if ke_hoach['error']:
        raise ValidationError(ke_hoach['error'])
    ky_cong = ke_hoach['period']
    ds_ngay = kiem_tra_lich_lam_viec(ky_cong)
    return ky_cong, next(lich for lich in ds_ngay if lich.ngay == ngay)


@transaction.atomic
def ghi_nhan_cham_cong(nguoi_thuc_hien, thao_tac, ghi_chu=''):
    if not nguoi_thuc_hien.is_authenticated:
        raise PermissionDenied('Cần đăng nhập trước khi chấm công.')
    if thao_tac not in ('in', 'out'):
        raise ValidationError('Thao tác không hợp lệ.')

    hien_tai = timezone.localtime().replace(microsecond=0)
    hom_nay = hien_tai.date()
    gio_hien_tai = hien_tai.time()
    nhan_vien = (
        NhanVien.objects.select_for_update()
        .filter(nguoi_dung=nguoi_thuc_hien, dang_hoat_dong=True)
        .first()
    )
    if not nhan_vien:
        raise PermissionDenied('Tài khoản chưa liên kết nhân viên đang làm việc.')
    ky_cong, lich_ngay = dam_bao_lich_cham_cong(hom_nay, nguoi_thuc_hien)
    if ky_cong_da_khoa(ky_cong, nhan_vien.pk, hom_nay):
        raise ValidationError('Bảng công đã duyệt, không thể chấm công thêm.')
    if not lich_ngay or lich_ngay.loai_ngay != 'work':
        raise ValidationError('Hôm nay chưa có lịch làm việc thông thường được cấu hình.')
    ban_ghi = (
        ChamCong.objects.select_for_update()
        .filter(nhan_vien=nhan_vien, ngay=hom_nay)
        .first()
    )

    if thao_tac == 'in':
        if ban_ghi:
            raise ValidationError('Hôm nay đã có bản ghi chấm công. Không thể check-in lại.')
        ban_ghi = ChamCong(
            nhan_vien=nhan_vien, ngay=hom_nay,
            gio_vao=gio_hien_tai, trang_thai='incomplete',
        )
        ban_ghi.full_clean()
    else:  # Thao tác đã được kiểm tra ở đầu hàm, nên đây là check-out.
        if not ban_ghi or not ban_ghi.gio_vao:
            raise ValidationError('Bạn cần check-in trước.')
        if ban_ghi.gio_ra or ban_ghi.trang_thai != 'incomplete':
            raise ValidationError('Bản ghi đã kết thúc hoặc cần nhân sự kiểm tra.')
        # Dùng lại nhân viên đã lấy, tránh truy vấn khóa ngoại khi tính công.
        ban_ghi.nhan_vien = nhan_vien
        ban_ghi.gio_ra = gio_hien_tai
        ban_ghi.trang_thai = 'present'
        tinh_cong_ngay(ban_ghi, ky_cong)

    ban_ghi.save()
    cap_nhat_tong_hop(nhan_vien, ky_cong)
    return ban_ghi
