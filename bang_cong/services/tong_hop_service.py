"""Tổng hợp công tháng cho màn hình Bảng công và dữ liệu tính lương."""

from collections import defaultdict
from decimal import Decimal

from django.db import transaction

from bang_cong.models import ChamCong, ChotBangCong, TongHopCong
from bang_cong.services.cham_cong_service import cong_chuan_thang, nap_cong_ngay


NHAN_TRANG_THAI_BANG_CONG = {
    'approved': 'Đã chốt',
    'pending': 'Chờ chốt',
    'incomplete': 'Cần kiểm tra',
    'empty': 'Chưa có dữ liệu',
}
ZERO = Decimal('0')


def _tinh_tong_hop(ban_ghi, nam, thang, cong_chuan, da_chot):
    cong_thuc_te = cong_nghi = gio_tang_ca = gio_lam = ZERO
    so_ngay_vang = so_lan_tre = so_phut_tre = 0
    thieu_du_lieu = False
    for cong in ban_ghi:
        cong_thuc_te += cong.cong_thuc_te
        cong_nghi += cong.cong_nghi_co_luong
        gio_tang_ca += cong.so_gio_tang_ca
        gio_lam += cong.so_gio_lam
        so_ngay_vang += cong.trang_thai == 'absent'
        so_lan_tre += cong.so_phut_tre > 0
        so_phut_tre += cong.so_phut_tre
        thieu_du_lieu |= cong.trang_thai == 'incomplete'

    trang_thai = 'empty'
    if da_chot:
        trang_thai = 'approved'
    elif ban_ghi:
        trang_thai = 'incomplete' if thieu_du_lieu else 'pending'

    return {
        'nam': nam,
        'thang': thang,
        'cong_chuan': cong_chuan,
        'cong_thuc_te': cong_thuc_te,
        'cong_nghi_co_luong': cong_nghi,
        'so_ngay_khong_phep': so_ngay_vang,
        'tong_cong': cong_thuc_te + cong_nghi,
        'tong_gio_tang_ca': gio_tang_ca,
        'so_lan_tre': so_lan_tre,
        'so_phut_tre': so_phut_tre,
        'trang_thai': trang_thai,
    }, gio_lam, bool(ban_ghi)


def _tong_hop_theo_nhan_vien(ma_nhan_vien, nam, thang, ds_ban_ghi=None):
    if ds_ban_ghi is None:
        ds_ban_ghi = ChamCong.objects.filter(
            ngay__year=nam, ngay__month=thang, nhan_vien_id__in=ma_nhan_vien,
        ).select_related('nhan_vien')
    records = list(ds_ban_ghi)
    if records:
        nap_cong_ngay(records, nam, thang)

    theo_nhan_vien = defaultdict(list)
    for record in records:
        theo_nhan_vien[record.nhan_vien_id].append(record)

    da_chot = set(ChotBangCong.objects.filter(
        tong_hop__nam=nam, tong_hop__thang=thang, tong_hop__nhan_vien_id__in=ma_nhan_vien,
    ).values_list('tong_hop__nhan_vien_id', flat=True))
    cong_chuan = cong_chuan_thang(nam, thang)
    return {
        ma: _tinh_tong_hop(theo_nhan_vien[ma], nam, thang, cong_chuan, ma in da_chot)
        for ma in ma_nhan_vien
    }


def tong_hop_cong_thang(ds_nhan_vien, nam, thang, *, ds_ban_ghi=None):
    """Tổng hợp dữ liệu hiển thị cho cả danh sách bằng truy vấn theo nhóm."""
    ds_nhan_vien = list(ds_nhan_vien)
    if not ds_nhan_vien:
        return []

    tong_hop = _tong_hop_theo_nhan_vien(
        [nhan_vien.pk for nhan_vien in ds_nhan_vien], nam, thang, ds_ban_ghi,
    )
    rows = []
    for nhan_vien in ds_nhan_vien:
        data, gio_lam, co_ban_ghi = tong_hop[nhan_vien.pk]
        trang_thai = data['trang_thai'] if co_ban_ghi else 'empty'
        rows.append({
            'employee': nhan_vien,
            'standard': data['cong_chuan'],
            'paid': data['tong_cong'],
            'actual': data['cong_thuc_te'],
            'leave': data['cong_nghi_co_luong'],
            'hours': gio_lam,
            'overtime': data['tong_gio_tang_ca'],
            'late': data['so_phut_tre'],
            'late_count': data['so_lan_tre'],
            'absent': data['so_ngay_khong_phep'],
            'state': trang_thai,
            'state_label': NHAN_TRANG_THAI_BANG_CONG[trang_thai],
            'has_records': co_ban_ghi,
        })
    return rows


def du_lieu_tong_hop(nhan_vien, nam, thang):
    """Tính dữ liệu dùng để lưu tổng hợp công tháng của một nhân viên."""
    tong_hop = _tong_hop_theo_nhan_vien([nhan_vien.pk], nam, thang)
    data, _, _ = tong_hop[nhan_vien.pk]
    return data


@transaction.atomic
def cap_nhat_tong_hop(nhan_vien, nam, thang):
    """Tạo hoặc cập nhật tổng hợp công của một nhân viên trong tháng."""
    summary, _ = TongHopCong.objects.update_or_create(
        nhan_vien=nhan_vien,
        nam=nam,
        thang=thang,
        defaults=du_lieu_tong_hop(nhan_vien, nam, thang),
    )
    return summary
