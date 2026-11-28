from decimal import Decimal
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from bang_cong.filters import BoLocCongCaNhan, NHAN_TINH_TRANG_CONG
from bang_cong.models import ChamCong
from bang_cong.services.cham_cong_service import tinh_tang_ca_tu_dong
from bang_cong.services.tong_hop_service import tong_hop_cong_thang
from nhan_vien.access import (
    co_vai_tro, nhan_vien_duoc_hien_thi, NHAN_SU, GIAM_DOC, TRUONG_PHONG,
)
from nhan_vien.models import NhanVien

KHONG = Decimal('0')
THU_TRONG_TUAN = ('T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN')


def _danh_sach_cong_ngay(ds_ban_ghi):
    cac_dong = []
    for ban_ghi in ds_ban_ghi:
        if ban_ghi.gio_vao is None and ban_ghi.gio_ra is None:
            continue
        ngay = ban_ghi.ngay
        trang_thai = {
            'present': 'late' if ban_ghi.so_phut_tre else 'ontime',
            'leave': 'paid_leave' if ban_ghi.cong_nghi_co_luong else 'unpaid_leave',
            'absent': 'absent',
        }.get(ban_ghi.trang_thai, 'incomplete')
        tang_ca = tinh_tang_ca_tu_dong(ban_ghi)
        cac_dong.append({
            'ngay': ngay, 'thu': THU_TRONG_TUAN[ngay.weekday()], 'ban_ghi': ban_ghi,
            'ma_trang_thai': trang_thai, 'trang_thai': NHAN_TINH_TRANG_CONG[trang_thai],
            'tang_ca': tang_ca.get('hours', KHONG),
            'loi_tang_ca': tang_ca.get('error', ''), 'canh_bao_tang_ca': tang_ca.get('warnings', []),
        })
    return cac_dong


def _du_lieu_cong_thang(yeu_cau, nhan_vien):
    hom_nay = timezone.localdate()
    nam_mac_dinh = min(max(hom_nay.year, 2020), 2030)
    try:
        thang = int(yeu_cau.GET.get('thang', hom_nay.month))
        nam = int(yeu_cau.GET.get('nam', nam_mac_dinh))
    except (TypeError, ValueError):
        thang, nam = hom_nay.month, nam_mac_dinh
    if not (1 <= thang <= 12 and 2020 <= nam <= 2030):
        thang, nam = hom_nay.month, nam_mac_dinh

    ds_ban_ghi = list(ChamCong.objects.filter(
        nhan_vien=nhan_vien, ngay__year=nam, ngay__month=thang,
    ).select_related('nhan_vien').order_by('-ngay'))
    tong_hop = tong_hop_cong_thang(
        [nhan_vien], nam, thang,
        ds_ban_ghi=ds_ban_ghi,
    )[0]
    cac_dong = _danh_sach_cong_ngay(ds_ban_ghi)
    ti_le_cong = 0
    if tong_hop['standard']:
        ti_le_cong = max(0, min(100, int(tong_hop['paid'] / tong_hop['standard'] * 100)))

    return {
        'thang': thang, 'nam': nam, 'cac_dong': cac_dong, 'tong_hop': tong_hop,
        'co_ky_cong': True, 'ti_le_cong': ti_le_cong,
        'tham_so_ky': urlencode({'thang': thang, 'nam': nam}),
    }


@login_required
def bang_cong_nhan_vien(yeu_cau, employee_id, chi_xem_ban_than=False):
    pham_vi = (
        NhanVien.objects.filter(nguoi_dung=yeu_cau.user)
        if chi_xem_ban_than else nhan_vien_duoc_hien_thi(yeu_cau.user)
    )
    nhan_vien = get_object_or_404(pham_vi, pk=employee_id)
    ngu_canh = _du_lieu_cong_thang(yeu_cau, nhan_vien)
    ca_nhan = chi_xem_ban_than or not co_vai_tro(
        yeu_cau.user, NHAN_SU, GIAM_DOC, TRUONG_PHONG,
    )
    if chi_xem_ban_than:
        bo_loc = BoLocCongCaNhan(yeu_cau.GET)
        ngu_canh['bo_loc_ca_nhan'] = bo_loc
        if bo_loc.is_valid():
            tu_ngay = bo_loc.cleaned_data['tu_ngay']
            den_ngay = bo_loc.cleaned_data['den_ngay']
            trang_thai = bo_loc.cleaned_data['trang_thai']
            cac_dong = ngu_canh['cac_dong']
            if tu_ngay or den_ngay:
                ds_ban_ghi = ChamCong.objects.filter(nhan_vien=nhan_vien)
                if tu_ngay:
                    ds_ban_ghi = ds_ban_ghi.filter(ngay__gte=tu_ngay)
                if den_ngay:
                    ds_ban_ghi = ds_ban_ghi.filter(ngay__lte=den_ngay)
                cac_dong = _danh_sach_cong_ngay(ds_ban_ghi.select_related('nhan_vien').order_by('-ngay'))
            if trang_thai:
                cac_dong = [dong for dong in cac_dong if dong['ma_trang_thai'] == trang_thai]
            ngu_canh.update(cac_dong=cac_dong, tu_ngay=tu_ngay, den_ngay=den_ngay)
        else:
            ngu_canh['cac_dong'] = []
    ngu_canh.update({
        'nhan_vien': nhan_vien,
        'ca_nhan': ca_nhan,
        'la_giam_doc': co_vai_tro(yeu_cau.user, GIAM_DOC),
        'chu_cai_dau': ''.join(phan_ten[0] for phan_ten in nhan_vien.ho_va_ten.split()[-2:]).upper(),
        'cac_tab': [('', 'Tất cả'), ('late', 'Đi trễ'), ('leave', 'Nghỉ phép'),
                 ('absent', 'Nghỉ không phép')],
    })
    mau_giao_dien = 'bang_cong/ca_nhan.html' if ca_nhan else 'bang_cong/chi_tiet.html'
    return render(yeu_cau, mau_giao_dien, ngu_canh)
