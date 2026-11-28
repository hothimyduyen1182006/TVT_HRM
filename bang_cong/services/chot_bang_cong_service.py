"""Xử lý chốt bảng công theo nhân viên."""

from django.core.exceptions import ValidationError
from django.db import transaction

from bang_cong.models import ChamCong, ChotBangCong
from nhan_vien.access import NHAN_SU, yeu_cau_vai_tro
from nhan_vien.models import NhanVien


def ky_cong_da_khoa(nam, thang, ma_nhan_vien):
    """Kiểm tra bản chốt của nhân viên trong tháng."""
    return ChotBangCong.objects.filter(
        tong_hop__nam=nam,
        tong_hop__thang=thang,
        tong_hop__nhan_vien_id=ma_nhan_vien,
    ).exists()


@transaction.atomic
def duyet_cong_nhan_vien(nguoi_thuc_hien, nhan_vien, ma_ky_cong):
    """Kiểm tra và chốt bảng công của một nhân viên trong kỳ."""
    yeu_cau_vai_tro(nguoi_thuc_hien, NHAN_SU)
    ma_ky_cong = int(ma_ky_cong)
    nam, thang = ma_ky_cong // 100, ma_ky_cong % 100
    nhan_vien = NhanVien.objects.select_for_update().get(pk=nhan_vien.pk)
    if ky_cong_da_khoa(nam, thang, nhan_vien.pk):
        raise ValidationError('Bảng công nhân viên này đã được chốt.')

    from .tong_hop_service import cap_nhat_tong_hop

    tong_hop = cap_nhat_tong_hop(nhan_vien, nam, thang)
    if tong_hop.trang_thai == 'empty' or ChamCong.objects.filter(
        nhan_vien=nhan_vien, ngay__year=nam, ngay__month=thang, trang_thai='incomplete',
    ).exists():
        raise ValidationError('Bảng công nhân viên chưa có dữ liệu hoặc còn bản ghi thiếu thông tin.')

    ban_chot = ChotBangCong.objects.create(
        tong_hop=tong_hop, nguoi_duyet=nguoi_thuc_hien,
    )
    tong_hop.trang_thai = 'approved'
    tong_hop.save(update_fields=['trang_thai'])

    from thuong.services.quy_trinh import dong_bo_thuong_tu_dong

    dong_bo_thuong_tu_dong(nhan_vien, thang, nam)
    return ban_chot
