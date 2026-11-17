"""Tính thưởng chuyên cần và thâm niên tự động."""
import calendar
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError

from bang_cong.models import TongHopCong


def tinh_thuong_tham_nien(nhan_vien, thang, nam):
    ngay_ket_thuc_ky = date(nam, thang, calendar.monthrange(nam, thang)[1])
    so_nam_da_lam = ngay_ket_thuc_ky.year - nhan_vien.ngay_vao_lam.year
    chua_den_ngay_ky_niem = (ngay_ket_thuc_ky.month, ngay_ket_thuc_ky.day) < (
        nhan_vien.ngay_vao_lam.month, nhan_vien.ngay_vao_lam.day
    )
    so_nam_tham_nien = max(0, so_nam_da_lam - chua_den_ngay_ky_niem)

    if so_nam_tham_nien < 1:
        muc_thuong = Decimal(0)
    elif so_nam_tham_nien < 3:
        muc_thuong = Decimal(150000)
    elif so_nam_tham_nien < 5:
        muc_thuong = Decimal(200000)
    else:
        muc_thuong = Decimal(500000)

    so_tien = so_nam_tham_nien * muc_thuong
    ly_do = f'{so_nam_tham_nien} năm thâm niên; mức thưởng tháng áp dụng {muc_thuong:,.0f} VNĐ.'
    return 'seniority', 'Thưởng thâm niên', so_tien, ly_do


def tinh_thuong_chuyen_can(nhan_vien, thang, nam):
    cong = TongHopCong.objects.filter(
        nhan_vien=nhan_vien, thang=thang, nam=nam, chotbangcong__isnull=False,
    ).first()
    if not cong:
        raise ValidationError(f'Bảng công của {nhan_vien} chưa được duyệt.')
    du_cong = (cong.cong_chuan > 0 and cong.cong_thuc_te >= cong.cong_chuan
               and cong.so_ngay_khong_phep == 0 and cong.cong_nghi_co_luong == 0)
    so_tien = Decimal(200000 if du_cong else 0)
    ly_do = ('Đủ ngày công quy định, không có ngày vắng mặt.' if du_cong
             else 'Không đạt thưởng chuyên cần do chưa đủ ngày công quy định hoặc có ngày vắng mặt.')
    return 'attendance', 'Thưởng chuyên cần', so_tien, ly_do


def tinh_thuong_tu_dong(nhan_vien, thang, nam):
    cac_khoan = [tinh_thuong_tham_nien(nhan_vien, thang, nam)]
    try:
        cac_khoan.append(tinh_thuong_chuyen_can(nhan_vien, thang, nam))
    except ValidationError as exc:
        return cac_khoan, exc
    return cac_khoan, None
