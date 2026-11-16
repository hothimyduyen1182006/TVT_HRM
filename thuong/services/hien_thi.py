"""Lọc và chuẩn bị dữ liệu hiển thị thưởng."""
from decimal import Decimal

from django.db import connection
from django.db.models import Q
from django.utils.dateparse import parse_datetime

from nhan_vien.access import nhan_vien_duoc_hien_thi
from ..models import DeXuatThuong, Thuong


def nguon_thuong_truoc_chuyen_doi(bang):
    """Chỉ đọc dữ liệu lưu trữ để giữ nguyên mã nguồn của phiếu lương cũ."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT id, loai_thuong, ten, so_tien, thoi_gian_de_xuat '
                       'FROM Khoan_thuong_luu_tru WHERE nhan_vien_id=%s AND nam=%s AND thang=%s',
                       [bang.nguoi_dung.employee.pk, bang.nam, bang.thang])
        return [{'id': ma, 'ma_moi': ('D' + str(ma).zfill(24) if loai == 'other' else f'{bang.pk}:{loai}'),
                 'name': ten, 'amount': format(Decimal(str(tien)), '.2f'),
                 'ngay': parse_datetime(ngay) if isinstance(ngay, str) else ngay}
                for ma, loai, ten, tien, ngay in cursor.fetchall()]


def gan_ma_hien_thi(cac_bang):
    """Giữ mã MT cũ trên giao diện, không đổi khóa liên kết với lương."""
    for bang in cac_bang:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM Khoan_thuong_luu_tru "
                "WHERE nhan_vien_id=%s AND nam=%s AND thang=%s "
                "ORDER BY CASE loai_thuong WHEN 'seniority' THEN 0 "
                "WHEN 'attendance' THEN 1 ELSE 2 END, ten, id LIMIT 1",
                [bang.nguoi_dung.employee.pk, bang.nam, bang.thang])
            cu = cursor.fetchone()
        bang.ma_hien_thi = (f'MT_{cu[0]:03d}' if cu else
                            f'MT_{bang.nam}{bang.thang:02d}_{bang.nguoi_dung_id}')
    return cac_bang


def cac_khoan_hien_thi(bang, nguon_cu=None):
    ket_qua = []
    if nguon_cu is None:
        nguon_cu = nguon_thuong_truoc_chuyen_doi(bang)
    for loai, ten, tien, ly_do in [
        ('seniority', 'Thưởng thâm niên', bang.thuong_tham_nien, bang.ly_do_tham_nien),
        ('attendance', 'Thưởng chuyên cần', bang.thuong_chuyen_can, bang.ly_do_chuyen_can),
    ]:
        if ly_do is not None:
            ma = f'{bang.pk}:{loai}'
            ngay = next((r['ngay'] for r in nguon_cu if r['ma_moi'] == ma), None)
            ket_qua.append({'id': ma, 'ten': ten, 'nhan_de_loai': ten, 'so_tien': tien,
                           'ly_do': ly_do, 'tu_dong': True, 'thoi_gian_de_xuat': ngay})
    for de_xuat in bang.de_xuat.order_by('ten', 'pk'):
        ket_qua.append({'id': de_xuat.pk, 'ten': de_xuat.ten, 'nhan_de_loai': de_xuat.ten,
                       'so_tien': de_xuat.so_tien, 'ly_do': de_xuat.ly_do, 'tu_dong': False,
                       'thoi_gian_de_xuat': de_xuat.thoi_gian_de_xuat})
    return ket_qua


def bang_thuong_trong_pham_vi(nguoi_dung):
    return Thuong.objects.select_related('nguoi_dung__employee__phong_ban', 'nguoi_duyet').filter(
        nguoi_dung__employee__in=nhan_vien_duoc_hien_thi(nguoi_dung))


def loc_bang_thuong(cac_bang, du_lieu):
    for cot in ['thang', 'nam', 'trang_thai']:
        if du_lieu.get(cot):
            cac_bang = cac_bang.filter(**{cot: du_lieu[cot]})
    if du_lieu.get('nhan_vien'):
        cac_bang = cac_bang.filter(nguoi_dung__employee=du_lieu['nhan_vien'])
    if du_lieu.get('phong_ban'):
        cac_bang = cac_bang.filter(nguoi_dung__employee__phong_ban=du_lieu['phong_ban'])
    if du_lieu.get('tu_khoa'):
        cac_bang = cac_bang.filter(Q(nguoi_dung__employee__ho_va_ten__icontains=du_lieu['tu_khoa'])
                                  | Q(nguoi_dung__employee__ma_ho_so__icontains=du_lieu['tu_khoa']))
    return cac_bang


def lich_su_de_xuat(nguoi_dung):
    return DeXuatThuong.objects.select_related('bang_thuong__nguoi_dung__employee__phong_ban').filter(
        bang_thuong__nguoi_dung__employee__in=nhan_vien_duoc_hien_thi(nguoi_dung), nguoi_de_xuat=nguoi_dung
    ).order_by('-thoi_gian_de_xuat', '-pk')


def lich_su_de_xuat_trong_pham_vi(nguoi_dung):
    return DeXuatThuong.objects.select_related('bang_thuong').filter(
        bang_thuong__nguoi_dung__employee__in=nhan_vien_duoc_hien_thi(nguoi_dung),
        bang_thuong__trang_thai__in=['draft', 'rejected'])
