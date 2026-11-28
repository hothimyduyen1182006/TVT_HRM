"""Tổng hợp công tháng cho màn hình Bảng công và dữ liệu tính lương."""

from collections import defaultdict
from decimal import Decimal

from django.db import transaction

from bang_cong.models import ChamCong, ChotBangCong, TongHopCong
from bang_cong.services.cham_cong_service import cong_chuan_thang, nap_cong_ngay


ZERO = Decimal('0')


def tong_hop_theo_nhan_vien(ds_nhan_vien, nam, thang, ds_ban_ghi=None, hien_thi=True):
    """Gom bản ghi theo nhân viên rồi tính tổng công tháng cho từng người."""
    ds_nhan_vien = list(ds_nhan_vien)
    if not ds_nhan_vien:
        return []

    ma_nhan_vien = [nhan_vien.pk for nhan_vien in ds_nhan_vien]
    if ds_ban_ghi is None:
        ds_ban_ghi = ChamCong.objects.filter(
            ngay__year=nam, ngay__month=thang, nhan_vien_id__in=ma_nhan_vien,
        ).select_related('nhan_vien')
    cac_ban_ghi = list(ds_ban_ghi)
    if cac_ban_ghi:
        nap_cong_ngay(cac_ban_ghi, nam, thang)

    theo_nhan_vien = defaultdict(list)
    for ban_ghi_ngay in cac_ban_ghi:
        theo_nhan_vien[ban_ghi_ngay.nhan_vien_id].append(ban_ghi_ngay)

    da_chot = set(ChotBangCong.objects.filter(
        tong_hop__nam=nam, tong_hop__thang=thang, tong_hop__nhan_vien_id__in=ma_nhan_vien,
    ).values_list('tong_hop__nhan_vien_id', flat=True))
    cong_chuan = cong_chuan_thang(nam, thang)
    ket_qua = []
    for nhan_vien in ds_nhan_vien:
        ma = nhan_vien.pk
        data, gio_lam, co_ban_ghi, thieu_du_lieu = _tinh_tong_hop(
            theo_nhan_vien[ma], cong_chuan, ma in da_chot,
        )
        if not hien_thi:
            ket_qua.append(data)
            continue

        trang_thai = data['trang_thai'] if co_ban_ghi else 'empty'
        ket_qua.append({
            **data,
            'nhan_vien': nhan_vien,
            'hours': gio_lam,
            'trang_thai': trang_thai,
            'nhan_trang_thai': TongHopCong(trang_thai=trang_thai).get_trang_thai_display(),
            'co_ban_ghi': co_ban_ghi,
            'co_the_chot': trang_thai == 'pending' and not thieu_du_lieu,
        })
    return ket_qua


def _tinh_tong_hop(ban_ghi_nhan_vien, cong_chuan, da_chot):
    """Cộng dồn công ngày của một nhân viên trong tháng."""
    cong_thuc_te = cong_nghi = gio_tang_ca = gio_lam = ZERO
    so_ngay_vang = so_lan_tre = so_phut_tre = 0
    thieu_du_lieu = False
    for ban_ghi_ngay in ban_ghi_nhan_vien:
        cong_thuc_te += ban_ghi_ngay.cong_thuc_te
        cong_nghi += ban_ghi_ngay.cong_nghi_co_luong
        gio_tang_ca += ban_ghi_ngay.so_gio_tang_ca
        gio_lam += ban_ghi_ngay.so_gio_lam
        so_ngay_vang += ban_ghi_ngay.trang_thai == 'absent'
        so_lan_tre += ban_ghi_ngay.so_phut_tre > 0
        so_phut_tre += ban_ghi_ngay.so_phut_tre
        thieu_du_lieu |= ban_ghi_ngay.trang_thai == 'incomplete'

    co_ban_ghi = bool(ban_ghi_nhan_vien)
    trang_thai = 'empty'
    if da_chot:
        trang_thai = 'approved'
    elif co_ban_ghi:
        trang_thai = 'pending'

    return {
        'cong_chuan': cong_chuan,
        'cong_thuc_te': cong_thuc_te,
        'cong_nghi_co_luong': cong_nghi,
        'so_ngay_khong_phep': so_ngay_vang,
        'tong_cong': cong_thuc_te + cong_nghi,
        'tong_gio_tang_ca': gio_tang_ca,
        'so_lan_tre': so_lan_tre,
        'so_phut_tre': so_phut_tre,
        'trang_thai': trang_thai,
    }, gio_lam, co_ban_ghi, thieu_du_lieu


@transaction.atomic
def cap_nhat_tong_hop(nhan_vien, nam, thang):
    """Tạo hoặc cập nhật tổng hợp công của một nhân viên trong tháng."""
    du_lieu, = tong_hop_theo_nhan_vien([nhan_vien], nam, thang, hien_thi=False)
    summary, _ = TongHopCong.objects.update_or_create(
        nhan_vien=nhan_vien,
        nam=nam,
        thang=thang,
        defaults=du_lieu,
    )
    return summary
