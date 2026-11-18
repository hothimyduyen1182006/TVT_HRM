"""Tạo và đọc tổng hợp công tháng làm dữ liệu đầu vào cho bảng lương."""

import calendar
from datetime import date
from decimal import Decimal

from django.db import transaction

from bang_cong.models import ChamCong, ChotBangCong, TongHopCong
from bang_cong.services.cham_cong_service import lich_thang, nap_cong_ngay
from nhan_vien.models import NhanVien


def du_lieu_tong_hop(nhan_vien, ky_cong):
    """Tính các khoản công của một nhân viên trong kỳ công."""
    records = list(ChamCong.objects.filter(
        nhan_vien=nhan_vien,
        ngay__year=ky_cong.nam,
        ngay__month=ky_cong.thang,
    ).order_by('ngay'))
    lich = lich_thang(ky_cong.nam, ky_cong.thang, ky_cong)
    if records:
        nap_cong_ngay(records, ky_cong, lich)

    zero = Decimal('0')
    cong_thuc_te = sum((record.cong_thuc_te for record in records), zero)
    cong_nghi = sum((record.cong_nghi_co_luong for record in records), zero)
    cong_chuan = sum((ngay.cong_chuan for ngay in lich.values()), zero)
    gio_tang_ca = sum((record.so_gio_tang_ca for record in records), zero)
    so_phut_tre = sum(record.so_phut_tre for record in records)
    so_ngay_vang = sum(record.trang_thai == 'absent' for record in records)
    da_chot = ChotBangCong.objects.filter(
        tong_hop__nhan_vien=nhan_vien,
        tong_hop__nam=ky_cong.nam,
        tong_hop__thang=ky_cong.thang,
    ).exists()

    return {
        'thang': ky_cong.thang,
        'nam': ky_cong.nam,
        'cong_chuan': cong_chuan,
        'cong_thuc_te': cong_thuc_te,
        'cong_nghi_co_luong': cong_nghi,
        'so_ngay_khong_phep': so_ngay_vang,
        'tong_cong': cong_thuc_te + cong_nghi,
        'tong_gio_tang_ca': gio_tang_ca,
        'so_lan_tre': sum(record.so_phut_tre > 0 for record in records),
        'so_phut_tre': so_phut_tre,
        'trang_thai': (
            'approved' if da_chot else
            'incomplete' if any(record.trang_thai == 'incomplete' for record in records) else
            'pending' if records else 'empty'
        ),
    }


def tong_hop_dung_tinh_luong(nhan_vien, ky_cong):
    """Dùng tổng hợp đã lưu nếu khớp dữ liệu công hiện tại."""
    data = du_lieu_tong_hop(nhan_vien, ky_cong)
    saved = TongHopCong.objects.filter(
        nhan_vien=nhan_vien,
        nam=ky_cong.nam,
        thang=ky_cong.thang,
    ).first()
    if saved and all(getattr(saved, key) == value for key, value in data.items()):
        return saved
    return TongHopCong(nhan_vien=nhan_vien, **data)


@transaction.atomic
def cap_nhat_tong_hop(nhan_vien, ky_cong):
    """Lưu tổng hợp công tháng của một nhân viên."""
    data = du_lieu_tong_hop(nhan_vien, ky_cong)
    summary, _ = TongHopCong.objects.update_or_create(
        nhan_vien=nhan_vien,
        nam=ky_cong.nam,
        thang=ky_cong.thang,
        defaults=data,
    )
    return summary


def cap_nhat_tong_hop_ca_ky(ky_cong):
    """Cập nhật tổng hợp công của nhân viên đã vào làm trước cuối kỳ."""
    ngay_cuoi_ky = date(
        ky_cong.nam,
        ky_cong.thang,
        calendar.monthrange(ky_cong.nam, ky_cong.thang)[1],
    )
    for nhan_vien in NhanVien.objects.filter(ngay_vao_lam__lte=ngay_cuoi_ky):
        cap_nhat_tong_hop(nhan_vien, ky_cong)
