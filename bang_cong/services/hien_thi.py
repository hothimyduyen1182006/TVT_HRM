"""Dữ liệu hiển thị; không thay đổi công thức hoặc tạo bản ghi chấm công."""

import calendar
from datetime import date
from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import Count, Exists, F, OuterRef, Q, Sum
from django.utils import timezone

from bang_cong.forms import CAC_TRUONG_DIEU_CHINH, BoLocBangCong, BoLocLichSuCong
from bang_cong.models import ChamCong, ChotBangCong, LichSuDieuChinhCong
from bang_cong.thang_lich import thang_lich
from nhan_vien.models import NhanVien

from .tinh_toan import tinh_tang_ca_tu_dong, lich_thang, nap_cong_ngay

KHONG = Decimal(0)
CAC_THU = ('T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN')
NHAN_TONG_HOP = {
    'empty': 'Chưa có dữ liệu', 'approved': 'Đã duyệt',
    'pending': 'Chờ duyệt', 'incomplete': 'Cần kiểm tra',
}
def _lay_lich_thang(nam, thang):
    return lich_thang(nam, thang)


def _lay_cong_thang(nam, thang, **pham_vi):
    return ChamCong.objects.filter(ngay__year=nam, ngay__month=thang, **pham_vi).select_related('nhan_vien')


def tong_hop_cong_thang(ds_nhan_vien, nam, thang, ky_cong, *, ds_ban_ghi=None, lich_thang=None):
    if ds_ban_ghi is None:
        ds_ban_ghi = _lay_cong_thang(nam, thang, nhan_vien_id__in=ds_nhan_vien.values('pk'))
    nhom_cong = ds_ban_ghi.values('nhan_vien_id').annotate(
        hours=Sum('so_gio_lam'), late=Sum('so_phut_tre'),
        late_count=Count('pk', filter=Q(so_phut_tre__gt=0)),
        incomplete=Count('pk', filter=Q(trang_thai='incomplete')),
        absent=Count('pk', filter=Q(trang_thai='absent')),
    )
    cong_theo_nhan_vien = {dong['nhan_vien_id']: dong for dong in nhom_cong}
    if lich_thang is None:
        lich_thang = _lay_lich_thang(nam, thang)
    if ky_cong:
        nap_cong_ngay(ds_ban_ghi, ky_cong, lich_thang)
    for ban_ghi in ds_ban_ghi:
        du_lieu = cong_theo_nhan_vien[ban_ghi.nhan_vien_id]
        for khoa, gia_tri in [('actual', ban_ghi.cong_thuc_te), ('leave', ban_ghi.cong_nghi_co_luong), ('paid', ban_ghi.tong_cong)]:
            du_lieu[khoa] = du_lieu.get(khoa, KHONG) + gia_tri
    cong_chuan = sum((lich.cong_chuan for lich in lich_thang.values()), KHONG) if lich_thang else None
    ket_qua = []
    ds_ma_da_duyet = set()
    if ky_cong:
        ds_ma_da_duyet = set(ChotBangCong.objects.filter(tong_hop__nam=nam, tong_hop__thang=thang)
            .values_list('tong_hop__nhan_vien_id', flat=True))
    ky_da_duyet = ky_cong and ky_cong.trang_thai == 'approved'
    for nhan_vien in ds_nhan_vien:
        du_lieu = cong_theo_nhan_vien.get(nhan_vien.pk, {})
        trang_thai = 'empty'
        if du_lieu:
            trang_thai = 'incomplete' if du_lieu['incomplete'] else 'pending'
            if nhan_vien.pk in ds_ma_da_duyet or ky_da_duyet:
                trang_thai = 'approved'
        ket_qua.append({'employee': nhan_vien, 'standard': cong_chuan, 'paid': du_lieu.get('paid', KHONG),
            'actual': du_lieu.get('actual', KHONG), 'leave': du_lieu.get('leave', KHONG),
            'hours': du_lieu.get('hours', KHONG), 'late': du_lieu.get('late', 0), 'late_count': du_lieu.get('late_count', 0),
            'absent': du_lieu.get('absent', 0), 'state': trang_thai,
            'state_label': NHAN_TONG_HOP[trang_thai], 'has_records': bool(du_lieu)})
    return ket_qua


def danh_sach_cong_ngay(nhan_vien, nam, thang, *, ds_ban_ghi=None, lich_thang=None, ky_cong=None, tang_ca=None):
    if ds_ban_ghi is None:
        ds_ban_ghi = _lay_cong_thang(nam, thang, nhan_vien=nhan_vien)
    ds_ban_ghi = {ban_ghi.ngay: ban_ghi for ban_ghi in ds_ban_ghi}
    if lich_thang is None:
        lich_thang = _lay_lich_thang(nam, thang)
    if tang_ca is None:
        ky_cong = ky_cong or thang_lich(nam, thang)
        tang_ca = {dong.pk: tinh_tang_ca_tu_dong(dong, ky_cong, lich_thang.get(dong.ngay)) for dong in ds_ban_ghi.values()}
    ket_qua = []
    ngay_cuoi = calendar.monthrange(nam, thang)[1]
    hom_nay = timezone.localdate()
    if (nam, thang) == (hom_nay.year, hom_nay.month):
        ngay_cuoi = min(ngay_cuoi, hom_nay.day)
    for so_ngay in range(ngay_cuoi, 0, -1):
        gia_tri = date(nam, thang, so_ngay)
        if gia_tri < nhan_vien.ngay_vao_lam:
            continue
        ban_ghi, lich_ngay = ds_ban_ghi.get(gia_tri), lich_thang.get(gia_tri)
        trang_thai, nhan = 'incomplete', 'Chưa có dữ liệu'
        if ban_ghi:
            trang_thai, nhan = {
                'present': ('late', 'Đi làm trễ') if ban_ghi.so_phut_tre else ('present', 'Đi đúng giờ'),
                'leave': ('leave', 'Nghỉ có lương' if ban_ghi.cong_nghi_co_luong else 'Nghỉ không lương'),
                'absent': ('absent', 'Nghỉ không phép'),
            }.get(ban_ghi.trang_thai, ('incomplete', 'Thiếu dữ liệu'))
        elif lich_ngay and lich_ngay.loai_ngay != 'work':
            trang_thai = 'rest'
            nhan = lich_ngay.ghi_chu or ('Nghỉ lễ' if lich_ngay.loai_ngay == 'holiday' else 'Nghỉ hằng tuần')
        phan_tu = tang_ca.get(ban_ghi.pk, {}) if ban_ghi else {}
        ket_qua.append({'date': gia_tri, 'weekday': CAC_THU[gia_tri.weekday()],
            'record': ban_ghi, 'state': trang_thai, 'label': nhan, 'ot': phan_tu.get('hours', KHONG),
            'ot_error': phan_tu.get('error', ''),
            'ot_warnings': phan_tu.get('warnings', [])})
    return ket_qua


def lay_lich_su_cong(nhan_vien, nam, thang):
    return LichSuDieuChinhCong.objects.filter(
        cham_cong__nhan_vien=nhan_vien, cham_cong__ngay__year=nam, cham_cong__ngay__month=thang,
    ).select_related('nguoi_thuc_hien', 'cham_cong__nhan_vien').order_by('-ngay_dieu_chinh', '-pk')


def danh_sach_dieu_chinh(ds_dieu_chinh, truong=''):
    if truong:
        ds_dieu_chinh = ds_dieu_chinh.filter(truong_dieu_chinh=truong)
    nhan = dict(ChamCong._meta.get_field('trang_thai').choices)
    return [{
        'time': dong.ngay_dieu_chinh, 'date': dong.ngay_cong,
        'field': CAC_TRUONG_DIEU_CHINH.get(dong.truong_dieu_chinh, dong.truong_dieu_chinh),
        'old': nhan.get(dong.gia_tri_cu, dong.gia_tri_cu) if dong.truong_dieu_chinh == 'status' else dong.gia_tri_cu,
        'new': nhan.get(dong.gia_tri_moi, dong.gia_tri_moi) if dong.truong_dieu_chinh == 'status' else dong.gia_tri_moi,
        'actor': dong.nguoi_thuc_hien.get_full_name() or dong.nguoi_thuc_hien.username,
        'reason': dong.ly_do,
    } for dong in ds_dieu_chinh]


def du_lieu_cong_thang(request, nhan_vien):
    """Tổng hợp toàn bộ ngày công của tháng được chọn từ bảng tổng hợp."""
    hom_nay = timezone.localdate()
    try:
        thang = int(request.GET.get('month', hom_nay.month))
        nam = int(request.GET.get('year', hom_nay.year))
    except (TypeError, ValueError):
        thang, nam = hom_nay.month, hom_nay.year
    if not 1 <= thang <= 12 or not 2000 <= nam <= 2100:
        thang, nam = hom_nay.month, hom_nay.year
    ds_dong, tong_hop, ky_cong, tien_do, trung_binh = [], None, None, 0, '—'
    tham_so_thang = urlencode({'month': thang, 'year': nam})
    ky_cong = thang_lich(nam, thang)
    ds_ban_ghi = _lay_cong_thang(nam, thang, nhan_vien=nhan_vien)
    lich_thang = _lay_lich_thang(nam, thang)
    tang_ca = {ban_ghi.pk: tinh_tang_ca_tu_dong(ban_ghi, ky_cong, lich_thang.get(ban_ghi.ngay))
                for ban_ghi in ds_ban_ghi}
    tong_hop = tong_hop_cong_thang(
        NhanVien.objects.filter(pk=nhan_vien.pk), nam, thang, ky_cong,
        ds_ban_ghi=ds_ban_ghi, lich_thang=lich_thang,
    )[0]
    ds_dong = danh_sach_cong_ngay(
        nhan_vien, nam, thang, ds_ban_ghi=ds_ban_ghi,
        lich_thang=lich_thang, ky_cong=ky_cong, tang_ca=tang_ca,
    )
    so_ngay_co_gio_vao = sum(1 for dong in ds_dong if dong['record'] and dong['record'].gio_vao)
    if so_ngay_co_gio_vao:
        so_phut = int(tong_hop['hours'] * 60 / so_ngay_co_gio_vao)
        trung_binh = f'{so_phut // 60}:{so_phut % 60:02}'
    if tong_hop['standard']:
        tien_do = max(0, min(100, int(tong_hop['paid'] / tong_hop['standard'] * 100)))
    return {'month': thang, 'year': nam, 'rows': ds_dong, 'summary': tong_hop,
            'period': ky_cong, 'progress': tien_do, 'average': trung_binh,
            'month_query': tham_so_thang}


def du_lieu_lich_su_cong(request, nhan_vien):
    """Lọc lịch sử theo kỳ công và điều kiện người dùng đã chọn."""
    bo_loc_ky = BoLocBangCong(request.user, request.GET)
    ds_nhat_ky = LichSuDieuChinhCong.objects.none()
    tham_so_thang = ''
    ky_hop_le = bo_loc_ky.is_valid()
    if ky_hop_le:
        du_lieu = bo_loc_ky.cleaned_data
        tham_so_thang = urlencode({'month': du_lieu['month'], 'year': du_lieu['year']})
        ds_nhat_ky = lay_lich_su_cong(nhan_vien, du_lieu['year'], du_lieu['month'])
    bieu_mau = BoLocLichSuCong(request.GET, ds_nhat_ky)
    ds_dong = []
    if bieu_mau.is_valid() and ky_hop_le:
        du_lieu = bieu_mau.cleaned_data
        dieu_kien = {
            truong: du_lieu[khoa] for truong, khoa in (
                ('ngay_dieu_chinh__date__gte', 'start'), ('ngay_dieu_chinh__date__lte', 'end'),
                ('nguoi_thuc_hien', 'actor'),
            ) if du_lieu[khoa]
        }
        ds_nhat_ky = ds_nhat_ky.filter(**dieu_kien)
        ds_dong = danh_sach_dieu_chinh(ds_nhat_ky, du_lieu['field'])
    return {'form': bieu_mau, 'period_form': bo_loc_ky, 'rows': ds_dong, 'month_query': tham_so_thang}
