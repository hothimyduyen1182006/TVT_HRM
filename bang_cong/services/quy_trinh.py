"""Lưu và duyệt công; lịch sử chỉ ghi chỉnh sửa trước khi duyệt."""

import calendar
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from nhan_vien.access import yeu_cau_vai_tro, NHAN_SU, GIAM_DOC
from nhan_vien.models import NhanVien
from bang_cong.models import (
    ChamCong, ChotBangCong, TongHopCong,
)
from bang_cong.thang_lich import thang_lich, thang_tu_ma
from .tinh_toan import tinh_cong_ngay


def _ngay_cuoi_ky(ky_cong):
    return date(ky_cong.nam, ky_cong.thang, calendar.monthrange(ky_cong.nam, ky_cong.thang)[1])


def ky_cong_da_khoa(ky_cong, ma_nhan_vien, ngay_cong=None):
    if not ky_cong:
        return False
    if ky_cong.trang_thai == 'approved':
        return True
    return ky_cong.employee_approvals.filter(tong_hop__nhan_vien_id=ma_nhan_vien).exists()


def cham_cong_da_khoa(ban_ghi):
    ky_cong = thang_lich(ban_ghi.ngay.year, ban_ghi.ngay.month)
    return ky_cong_da_khoa(ky_cong, ban_ghi.nhan_vien_id, ban_ghi.ngay)


def _tinh_lai_cac_ban_ghi(ds_ban_ghi, ky_cong, nguoi_thuc_hien, ly_do):
    """Tính lại công và ghi lịch sử bằng cùng một luồng khi duyệt kỳ hoặc nhân viên."""
    for ban_ghi in ds_ban_ghi:
        tinh_cong_ngay(ban_ghi, ky_cong)
        ban_ghi.save()


def du_lieu_cham_cong(ban_ghi):
    # Giữ khóa JSON lịch sử để đối chiếu phiếu lương và nhật ký cũ.
    cac_truong = {
        'pk': 'pk', 'employee_id': 'nhan_vien_id', 'date': 'ngay',
        'check_in': 'gio_vao', 'check_out': 'gio_ra', 'status': 'trang_thai',
        'work_hours': 'so_gio_lam', 'late_minutes': 'so_phut_tre',
        'actual_units': 'cong_thuc_te', 'paid_leave_units': 'cong_nghi_co_luong',
        'paid_units': 'tong_cong', 'overtime_hours': 'gio_tang_ca',
    }
    return {khoa: str(getattr(ban_ghi, truong)) for khoa, truong in cac_truong.items()}


@transaction.atomic
def ghi_nhan_cham_cong(nguoi_thuc_hien, ban_ghi):
    """Tạo bản công mới; bản công đã tạo không thể sửa từ luồng này."""
    yeu_cau_vai_tro(nguoi_thuc_hien, NHAN_SU, GIAM_DOC)
    if ban_ghi.pk:
        raise ValidationError('Không hỗ trợ chỉnh sửa bản công đã ghi nhận.')
    ky_cong = thang_lich(ban_ghi.ngay.year, ban_ghi.ngay.month)
    if ky_cong_da_khoa(ky_cong, ban_ghi.nhan_vien_id, ban_ghi.ngay):
        raise ValidationError('Bảng công đã duyệt, không thể ghi thêm.')
    tinh_cong_ngay(ban_ghi, ky_cong)
    ban_ghi.save()
    cap_nhat_tong_hop(ban_ghi.nhan_vien, ky_cong)
    return ban_ghi

@transaction.atomic
def xu_ly_trang_thai_ky_cong(nguoi_thuc_hien, ma_ky_cong, thao_tac, ly_do):
    yeu_cau_vai_tro(nguoi_thuc_hien, GIAM_DOC)
    if thao_tac != 'approve':
        raise ValidationError('Chỉ được duyệt công; bảng công đã duyệt không được mở lại.')
    ky_cong = thang_tu_ma(ma_ky_cong)
    if not ly_do.strip():
        raise ValidationError('Cần ghi lý do.')
    if thao_tac == 'approve':
        if ky_cong.trang_thai != 'pending':
            raise ValidationError('Kỳ công phải đang chờ duyệt.')
        from .cham_cong_service import kiem_tra_lich_lam_viec
        lich_da_kiem_tra = kiem_tra_lich_lam_viec(ky_cong)
        ds_ban_ghi = ChamCong.objects.filter(ngay__year=ky_cong.nam, ngay__month=ky_cong.thang)
        ds_nhan_vien = NhanVien.objects.filter(dang_hoat_dong=True, ngay_vao_lam__lte=_ngay_cuoi_ky(ky_cong))
        for nhan_vien in ds_nhan_vien:
            ngay_bat_buoc = {lich_ngay.ngay for lich_ngay in lich_da_kiem_tra
                        if lich_ngay.loai_ngay == 'work' and lich_ngay.ngay >= nhan_vien.ngay_vao_lam}
            ngay_da_co = set(ds_ban_ghi.filter(nhan_vien=nhan_vien).exclude(trang_thai='incomplete').values_list('ngay', flat=True))
            if not set(ngay_bat_buoc).issubset(ngay_da_co):
                raise ValidationError(f'{nhan_vien}: còn ngày làm việc chưa kiểm tra.')
        _tinh_lai_cac_ban_ghi(ds_ban_ghi.exclude(nhan_vien_id__in=
            ky_cong.employee_approvals.values_list('tong_hop__nhan_vien_id', flat=True)), ky_cong, nguoi_thuc_hien, ly_do)
        for nhan_vien in ds_nhan_vien:
            tong_hop = cap_nhat_tong_hop(nhan_vien, ky_cong)
            ChotBangCong.objects.get_or_create(tong_hop=tong_hop, defaults={'nguoi_duyet': nguoi_thuc_hien})
    else:
        raise ValidationError('Thao tác không hợp lệ.')
    cap_nhat_tong_hop_ca_ky(ky_cong)
    if thao_tac == 'approve':
        from thuong.services.quy_trinh import dong_bo_thuong_tu_dong
        from bang_luong.services.tinh_toan import cap_nhat_luong_nhan_vien
        for ma_nhan_vien in ky_cong.ds_nhan_vien:
            dong_bo_thuong_tu_dong(NhanVien.objects.get(pk=ma_nhan_vien), ky_cong.thang, ky_cong.nam)
            cap_nhat_luong_nhan_vien(nguoi_thuc_hien, ma_nhan_vien, ky_cong.nam, ky_cong.thang)


@transaction.atomic
def duyet_cong_nhan_vien(nguoi_thuc_hien, nhan_vien, ma_ky_cong):
    yeu_cau_vai_tro(nguoi_thuc_hien, NHAN_SU, GIAM_DOC)
    ky_cong = thang_tu_ma(ma_ky_cong)
    if ky_cong_da_khoa(ky_cong, nhan_vien.pk):
        raise ValidationError('Bảng công nhân viên này đã được duyệt.')
    from .cham_cong_service import kiem_tra_lich_lam_viec
    lich_da_kiem_tra = kiem_tra_lich_lam_viec(ky_cong)
    ds_ban_ghi = ChamCong.objects.filter(nhan_vien=nhan_vien, ngay__year=ky_cong.nam, ngay__month=ky_cong.thang)
    ngay_bat_buoc = {lich_ngay.ngay for lich_ngay in lich_da_kiem_tra
                if lich_ngay.loai_ngay == 'work' and lich_ngay.ngay >= nhan_vien.ngay_vao_lam}
    ngay_da_co = set(ds_ban_ghi.exclude(trang_thai='incomplete').values_list('ngay', flat=True))
    if not ds_ban_ghi.exists() or not ngay_bat_buoc.issubset(ngay_da_co) or ds_ban_ghi.filter(trang_thai='incomplete').exists():
        raise ValidationError('Bảng công nhân viên còn thiếu ngày hoặc có dữ liệu chưa kiểm tra.')
    _tinh_lai_cac_ban_ghi(ds_ban_ghi, ky_cong, nguoi_thuc_hien, 'Tính lại trước khi duyệt nhân viên')
    ban_chot = ky_cong.employee_approvals.filter(tong_hop__nhan_vien=nhan_vien).first()
    if ban_chot:
        ban_chot.nguoi_duyet = nguoi_thuc_hien
        ban_chot.ngay_duyet = timezone.now()
        ban_chot.save(update_fields=['nguoi_duyet', 'ngay_duyet'])
    else:
        ban_chot = ChotBangCong.objects.create(
            tong_hop=cap_nhat_tong_hop(nhan_vien, ky_cong), nguoi_duyet=nguoi_thuc_hien)
    cap_nhat_tong_hop(nhan_vien, ky_cong)
    from bang_luong.services.tinh_toan import cap_nhat_luong_nhan_vien
    from thuong.services.quy_trinh import dong_bo_thuong_tu_dong
    dong_bo_thuong_tu_dong(nhan_vien, ky_cong.thang, ky_cong.nam)
    ban_chot.payroll_error = cap_nhat_luong_nhan_vien(nguoi_thuc_hien, nhan_vien.pk, ky_cong.nam, ky_cong.thang)
    return ban_chot


def du_lieu_tong_hop(nhan_vien, ky_cong):
    from .tong_hop_service import du_lieu_tong_hop as tong_hop
    return tong_hop(nhan_vien, ky_cong)

def tong_hop_dung_tinh_luong(nhan_vien, ky_cong):
    """Đọc bản tổng hợp còn khớp nguồn; dữ liệu cũ chưa đồng bộ chỉ tính trong bộ nhớ."""
    du_lieu = du_lieu_tong_hop(nhan_vien, ky_cong)
    da_luu = TongHopCong.objects.filter(nhan_vien=nhan_vien, nam=ky_cong.nam, thang=ky_cong.thang).first()
    if da_luu and all(getattr(da_luu, khoa) == gia_tri for khoa, gia_tri in du_lieu.items()):
        return da_luu
    return TongHopCong(nhan_vien=nhan_vien, **du_lieu)


@transaction.atomic
def cap_nhat_tong_hop(nhan_vien, ky_cong):
    """Cập nhật một bản tổng hợp và nối với bản chốt còn thiếu liên kết."""
    tong_hop, _ = TongHopCong.objects.update_or_create(
        nhan_vien=nhan_vien, nam=ky_cong.nam, thang=ky_cong.thang,
        defaults=du_lieu_tong_hop(nhan_vien, ky_cong),
    )
    return tong_hop


def cap_nhat_tong_hop_ca_ky(ky_cong):
    """Đồng bộ tổng hợp của các nhân viên đã vào làm trước cuối kỳ."""
    for nhan_vien in NhanVien.objects.filter(ngay_vao_lam__lte=_ngay_cuoi_ky(ky_cong)):
        cap_nhat_tong_hop(nhan_vien, ky_cong)


