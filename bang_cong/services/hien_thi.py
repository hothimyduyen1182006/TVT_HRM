"""Dữ liệu hiển thị; không thay đổi công thức hoặc tạo bản ghi chấm công."""

import calendar
from datetime import date
from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import Count, Exists, F, OuterRef, Q, Sum

from bang_cong.forms import CAC_TRUONG_DIEU_CHINH, BoLocBangCong, BoLocCongNgay, BoLocLichSuCong
from bang_cong.models import ChamCong, ChotBangCong, KyCong, LichLamViec, NhatKyCong
from nhan_vien.models import Employee

from .tinh_toan import tinh_tang_ca_tu_dong

KHONG = Decimal(0)
CAC_THU = ('T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN')
NHAN_TONG_HOP = {
    'empty': 'Chưa có dữ liệu', 'approved': 'Đã duyệt',
    'pending': 'Chờ duyệt', 'incomplete': 'Cần kiểm tra',
}
TRUONG_LOC_CONG = {
    'paid': 'tong_cong', 'actual': 'cong_thuc_te', 'paid_leave': 'cong_nghi_co_luong',
}


def _lay_lich_thang(nam, thang):
    return {lich.ngay: lich for lich in LichLamViec.objects.filter(ngay__year=nam, ngay__month=thang)}


def _lay_cong_thang(nam, thang, **pham_vi):
    return ChamCong.objects.filter(ngay__year=nam, ngay__month=thang, **pham_vi).select_related('nhan_vien')


def du_lieu_tang_ca(ban_ghi):
    return {'automatic_ot': tinh_tang_ca_tu_dong(ban_ghi)}


def tong_hop_cong_thang(ds_nhan_vien, nam, thang, ky_cong, *, ds_ban_ghi=None, lich_thang=None, tang_ca=None):
    if ds_ban_ghi is None:
        ds_ban_ghi = _lay_cong_thang(nam, thang, nhan_vien_id__in=ds_nhan_vien.values('pk'))
    nhom_cong = ds_ban_ghi.values('nhan_vien_id').annotate(
        paid=Sum('tong_cong'), actual=Sum('cong_thuc_te'),
        leave=Sum('cong_nghi_co_luong'), hours=Sum('so_gio_lam'), late=Sum('so_phut_tre'),
        late_count=Count('pk', filter=Q(so_phut_tre__gt=0)),
        incomplete=Count('pk', filter=Q(trang_thai='incomplete')),
        absent=Count('pk', filter=Q(trang_thai='absent')),
    )
    cong_theo_nhan_vien = {dong['nhan_vien_id']: dong for dong in nhom_cong}
    if lich_thang is None:
        lich_thang = _lay_lich_thang(nam, thang)
    tong_ot_theo_nhan_vien = {}
    for ban_ghi in ds_ban_ghi:
        phan_tu = (tang_ca[ban_ghi.pk] if tang_ca is not None else
                tinh_tang_ca_tu_dong(ban_ghi, ky_cong, lich_thang.get(ban_ghi.ngay)))
        tong_ot_theo_nhan_vien[ban_ghi.nhan_vien_id] = tong_ot_theo_nhan_vien.get(ban_ghi.nhan_vien_id, KHONG) + phan_tu['hours']
    cong_chuan = sum((lich.cong_chuan for lich in lich_thang.values()), KHONG) if lich_thang else None
    ket_qua = []
    ds_ma_da_duyet = set()
    if ky_cong:
        cong_thay_doi_sau_duyet = ChamCong.objects.filter(
            nhan_vien_id=OuterRef('nhan_vien_id'), ngay__year=nam, ngay__month=thang,
            ngay_cap_nhat__gt=OuterRef('ngay_duyet'),
        )
        ds_ma_da_duyet = set(ChotBangCong.objects.filter(ky_cong=ky_cong)
            .annotate(co_thay_doi=Exists(cong_thay_doi_sau_duyet))
            .filter(co_thay_doi=False).values_list('nhan_vien_id', flat=True))
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
            'absent': du_lieu.get('absent', 0), 'ot': tong_ot_theo_nhan_vien.get(nhan_vien.pk,KHONG), 'state': trang_thai,
            'state_label': NHAN_TONG_HOP[trang_thai], 'has_records': bool(du_lieu)})
    return ket_qua


def danh_sach_cong_ngay(nhan_vien, nam, thang, *, ds_ban_ghi=None, lich_thang=None, ky_cong=None, tang_ca=None):
    if ds_ban_ghi is None:
        ds_ban_ghi = _lay_cong_thang(nam, thang, nhan_vien=nhan_vien)
    ds_ban_ghi = {ban_ghi.ngay: ban_ghi for ban_ghi in ds_ban_ghi}
    if lich_thang is None:
        lich_thang = _lay_lich_thang(nam, thang)
    if tang_ca is None:
        ky_cong = ky_cong or KyCong.objects.filter(nam=nam, thang=thang).first()
        tang_ca = {dong.pk: tinh_tang_ca_tu_dong(dong, ky_cong, lich_thang.get(dong.ngay)) for dong in ds_ban_ghi.values()}
    ket_qua = []
    for so_ngay in range(1, calendar.monthrange(nam, thang)[1] + 1):
        gia_tri = date(nam, thang, so_ngay)
        if gia_tri < nhan_vien.hire_date:
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


def lay_nhat_ky_cong(nhan_vien, nam, thang):
    # save_record là tên sự kiện cũ: chỉ giữ lần sửa có cả trước/sau, không lấy lần tạo.
    return (NhatKyCong.objects.filter(
        hanh_dong__in=['edit_record', 'save_record'],
        du_lieu_moi__employee_id=str(nhan_vien.pk),
        du_lieu_moi__date__startswith=f'{nam:04}-{thang:02}-')
        .exclude(du_lieu_cu={}).exclude(du_lieu_cu=F('du_lieu_moi'))
        .select_related('nguoi_thuc_hien').prefetch_related('adjustments')
        .order_by('-ngay_tao', '-pk'))


def danh_sach_dieu_chinh(ds_nhat_ky, truong=''):
    ket_qua = []
    cac_nhan = dict(ChamCong._meta.get_field('trang_thai').choices)
    cac_nhan.update({'pending': 'Chờ duyệt', 'approved': 'Đã duyệt'})
    cac_truong = [(khoa, ten) for khoa, ten in CAC_TRUONG_DIEU_CHINH.items() if not truong or khoa == truong]
    for nhat_ky in ds_nhat_ky:
        if nhat_ky.hanh_dong not in ['edit_record', 'save_record'] or not nhat_ky.du_lieu_cu or nhat_ky.du_lieu_cu == nhat_ky.du_lieu_moi:
            continue
        thay_doi = {phan_tu.truong_dieu_chinh: (phan_tu.gia_tri_cu, phan_tu.gia_tri_moi) for phan_tu in nhat_ky.adjustments.all()}
        nguoi_sua = nhat_ky.nguoi_thuc_hien.get_full_name() or nhat_ky.nguoi_thuc_hien.username
        for khoa, ten_truong in cac_truong:
            cu, moi = thay_doi.get(khoa, (nhat_ky.du_lieu_cu.get(khoa, ''), nhat_ky.du_lieu_moi.get(khoa, '')))
            if cu == moi:
                continue
            ket_qua.append({'time': nhat_ky.ngay_tao, 'date': nhat_ky.du_lieu_moi.get('date'), 'field': ten_truong,
                'old': cac_nhan.get(cu, cu) if khoa in ['status', 'approval_status'] else cu,
                'new': cac_nhan.get(moi, moi) if khoa in ['status', 'approval_status'] else moi,
                'actor': nguoi_sua, 'reason': nhat_ky.ly_do})
    return ket_qua


def du_lieu_cong_thang(request, nhan_vien):
    """Tổng hợp ngày công và bộ lọc cho một nhân viên, không thay đổi dữ liệu."""
    bieu_mau = BoLocCongNgay(request.user, request.GET)
    ds_dong, tong_hop, ky_cong, tien_do, trung_binh = [], None, None, 0, '—'
    tham_so_thang = ''
    hop_le = bieu_mau.is_valid()
    if hop_le:
        du_lieu = bieu_mau.cleaned_data
        tham_so_thang = urlencode({'month': du_lieu['month'], 'year': du_lieu['year']})
        ky_cong = KyCong.objects.filter(nam=du_lieu['year'], thang=du_lieu['month']).first()
        # Cùng một lần tải nguồn và tính OT cho tổng hợp lẫn bảng chi tiết.
        ds_ban_ghi = _lay_cong_thang(du_lieu['year'], du_lieu['month'], nhan_vien=nhan_vien)
        lich_thang = _lay_lich_thang(du_lieu['year'], du_lieu['month'])
        tang_ca = {ban_ghi.pk: tinh_tang_ca_tu_dong(ban_ghi, ky_cong, lich_thang.get(ban_ghi.ngay))
                    for ban_ghi in ds_ban_ghi}
        tong_hop = tong_hop_cong_thang(
            Employee.objects.filter(pk=nhan_vien.pk), du_lieu['year'], du_lieu['month'], ky_cong,
            ds_ban_ghi=ds_ban_ghi, lich_thang=lich_thang, tang_ca=tang_ca,
        )[0]
        ds_dong = danh_sach_cong_ngay(
            nhan_vien, du_lieu['year'], du_lieu['month'], ds_ban_ghi=ds_ban_ghi,
            lich_thang=lich_thang, ky_cong=ky_cong, tang_ca=tang_ca,
        )
        so_ngay_co_gio_vao = sum(1 for dong in ds_dong if dong['record'] and dong['record'].gio_vao)
        if so_ngay_co_gio_vao:
            so_phut = int(tong_hop['hours'] * 60 / so_ngay_co_gio_vao)
            trung_binh = f'{so_phut // 60}:{so_phut % 60:02}'
        if tong_hop['standard']:
            tien_do = max(0, min(100, int(tong_hop['paid'] / tong_hop['standard'] * 100)))
        if du_lieu['start'] or du_lieu['end']:
            ds_dong = [
                dong for dong in ds_dong
                if (not du_lieu['start'] or dong['date'] >= du_lieu['start'])
                and (not du_lieu['end'] or dong['date'] <= du_lieu['end'])
            ]
        if du_lieu['state']:
            trang_thai = du_lieu['state']
            truong_cong = TRUONG_LOC_CONG.get(trang_thai)
            if truong_cong:
                ds_dong = [dong for dong in ds_dong if dong['record'] and getattr(dong['record'], truong_cong) > 0]
            elif trang_thai == 'ot':
                ds_dong = [dong for dong in ds_dong if dong['ot'] > 0]
            else:
                ds_dong = [dong for dong in ds_dong if dong['state'] == trang_thai]
    tham_so_thong_ke = request.GET.copy()
    tham_so_thong_ke.pop('page', None)
    tham_so_thong_ke.pop('state', None)
    if hop_le:
        tham_so_thong_ke['month'] = bieu_mau.cleaned_data['month']
        tham_so_thong_ke['year'] = bieu_mau.cleaned_data['year']
    return {'form': bieu_mau, 'rows': ds_dong, 'summary': tong_hop, 'period': ky_cong, 'progress': tien_do,
            'average': trung_binh, 'month_query': tham_so_thang, 'stat_query': tham_so_thong_ke.urlencode()}


def du_lieu_lich_su_cong(request, nhan_vien):
    """Lọc lịch sử theo kỳ công và điều kiện người dùng đã chọn."""
    bo_loc_ky = BoLocBangCong(request.user, request.GET)
    ds_nhat_ky = NhatKyCong.objects.none()
    tham_so_thang = ''
    ky_hop_le = bo_loc_ky.is_valid()
    if ky_hop_le:
        du_lieu = bo_loc_ky.cleaned_data
        tham_so_thang = urlencode({'month': du_lieu['month'], 'year': du_lieu['year']})
        ds_nhat_ky = lay_nhat_ky_cong(nhan_vien, du_lieu['year'], du_lieu['month'])
    bieu_mau = BoLocLichSuCong(request.GET, ds_nhat_ky)
    ds_dong = []
    if bieu_mau.is_valid() and ky_hop_le:
        du_lieu = bieu_mau.cleaned_data
        dieu_kien = {
            truong: du_lieu[khoa] for truong, khoa in (
                ('ngay_tao__date__gte', 'start'), ('ngay_tao__date__lte', 'end'),
                ('nguoi_thuc_hien', 'actor'),
            ) if du_lieu[khoa]
        }
        ds_nhat_ky = ds_nhat_ky.filter(**dieu_kien)
        ds_dong = danh_sach_dieu_chinh(ds_nhat_ky, du_lieu['field'])
    return {'form': bieu_mau, 'period_form': bo_loc_ky, 'rows': ds_dong, 'month_query': tham_so_thang}
