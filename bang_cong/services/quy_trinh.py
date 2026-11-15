"""Lưu và duyệt công; lịch sử chỉ ghi chỉnh sửa trước khi duyệt."""

import calendar
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from nhan_vien.access import yeu_cau_vai_tro, NHAN_SU, GIAM_DOC
from nhan_vien.models import NhanVien
from bang_cong.models import (
    ChamCong, ChotBangCong, TongHopCong, LichSuDieuChinhCong,
)
from bang_luong.models import PayrollPeriod
from .tinh_toan import tinh_cong_ngay, luu_can_cu_lich


def _ngay_cuoi_ky(ky_cong):
    return date(ky_cong.nam, ky_cong.thang, calendar.monthrange(ky_cong.nam, ky_cong.thang)[1])


def ky_cong_da_khoa(ky_cong, ma_nhan_vien, ngay_cong=None):
    if not ky_cong:
        return False
    if ky_cong.trang_thai == 'approved':
        return True
    return ky_cong.employee_approvals.filter(tong_hop__nhan_vien_id=ma_nhan_vien).exists()


def cham_cong_da_khoa(ban_ghi):
    ky_cong = PayrollPeriod.objects.filter(nam=ban_ghi.ngay.year, thang=ban_ghi.ngay.month).first()
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
def luu_cham_cong(nguoi_thuc_hien, ban_ghi, ly_do):
    yeu_cau_vai_tro(nguoi_thuc_hien, NHAN_SU, GIAM_DOC)
    if not ly_do.strip():
        raise ValidationError('Cần lý do thay đổi.')
    ky_cong = PayrollPeriod.objects.select_for_update().get(nam=ban_ghi.ngay.year, thang=ban_ghi.ngay.month)
    if ky_cong_da_khoa(ky_cong, ban_ghi.nhan_vien_id, ban_ghi.ngay):
        raise ValidationError('Bảng công đã duyệt, không được chỉnh sửa.')
    du_lieu_cu = {}
    if ban_ghi.pk:
        cu = ChamCong.objects.select_for_update().get(pk=ban_ghi.pk)
        if cu.nhan_vien_id != ban_ghi.nhan_vien_id or cu.ngay != ban_ghi.ngay:
            raise ValidationError('Không đổi nhân viên/ngày của bản ghi đã tạo.')
        du_lieu_cu = du_lieu_cham_cong(cu)
    tinh_cong_ngay(ban_ghi, ky_cong)
    ban_ghi.save()
    du_lieu_moi = du_lieu_cham_cong(ban_ghi)
    if du_lieu_cu != du_lieu_moi:
        ghi_lich_su_dieu_chinh(ban_ghi, nguoi_thuc_hien, ly_do, du_lieu_cu, du_lieu_moi)
    cap_nhat_tong_hop(ban_ghi.nhan_vien, ky_cong)
    return ban_ghi


@transaction.atomic
def xu_ly_trang_thai_ky_cong(nguoi_thuc_hien, ma_ky_cong, thao_tac, ly_do):
    require_role(nguoi_thuc_hien, DIRECTOR)
    if thao_tac != 'approve':
        raise ValidationError('Chỉ được duyệt công; bảng công đã duyệt không được mở lại.')
    ky_cong = PayrollPeriod.objects.select_for_update().get(pk=ma_ky_cong)
    if not ly_do.strip():
        raise ValidationError('Cần ghi lý do.')
    if thao_tac == 'approve':
        if ky_cong.trang_thai != 'pending':
            raise ValidationError('Kỳ công phải đang chờ duyệt.')
        from .cham_cong import kiem_tra_lich_lam_viec
        lich_da_kiem_tra = kiem_tra_lich_lam_viec(ky_cong)
        luu_can_cu_lich(ky_cong, lich_da_kiem_tra)
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
        ky_cong.trang_thai = 'approved'
        ky_cong.ds_nhan_vien = list(ds_nhan_vien.values_list('pk', flat=True))
        for nhan_vien in ds_nhan_vien:
            tong_hop = cap_nhat_tong_hop(nhan_vien, ky_cong)
            ChotBangCong.objects.get_or_create(tong_hop=tong_hop, defaults={'nguoi_duyet': nguoi_thuc_hien})
        ky_cong.nguoi_duyet = nguoi_thuc_hien
        ky_cong.ngay_duyet = timezone.now()
    else:
        raise ValidationError('Thao tác không hợp lệ.')
    ky_cong.save()
    cap_nhat_tong_hop_ca_ky(ky_cong)
    if thao_tac == 'approve':
        from bang_luong.services.tinh_toan import cap_nhat_luong_nhan_vien
        for ma_nhan_vien in ky_cong.ds_nhan_vien:
            cap_nhat_luong_nhan_vien(nguoi_thuc_hien, ma_nhan_vien, ky_cong.nam, ky_cong.thang)


@transaction.atomic
def duyet_cong_nhan_vien(nguoi_thuc_hien, nhan_vien, ma_ky_cong):
    require_role(nguoi_thuc_hien, HR, DIRECTOR)
    ky_cong = PayrollPeriod.objects.select_for_update().get(pk=ma_ky_cong)
    if ky_cong_da_khoa(ky_cong, nhan_vien.pk):
        raise ValidationError('Bảng công nhân viên này đã được duyệt.')
    from .cham_cong import kiem_tra_lich_lam_viec
    lich_da_kiem_tra = kiem_tra_lich_lam_viec(ky_cong)
    luu_can_cu_lich(ky_cong, lich_da_kiem_tra)
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
    ds_ma_nhan_vien = set(Employee.objects.filter(is_active=True,
        hire_date__lte=_ngay_cuoi_ky(ky_cong)).values_list('pk', flat=True))
    ma_da_duyet_hop_le = set(ky_cong.employee_approvals.values_list('tong_hop__nhan_vien_id', flat=True))
    if ds_ma_nhan_vien and ds_ma_nhan_vien.issubset(ma_da_duyet_hop_le):
        ky_cong.trang_thai = 'approved'
        ky_cong.ds_nhan_vien = sorted(ds_ma_nhan_vien)
        ky_cong.nguoi_duyet = nguoi_thuc_hien
        ky_cong.ngay_duyet = timezone.now()
        ky_cong.save()
    cap_nhat_tong_hop(nhan_vien, ky_cong)
    from bang_luong.services.tinh_toan import cap_nhat_luong_nhan_vien
    ban_chot.payroll_error = cap_nhat_luong_nhan_vien(nguoi_thuc_hien, nhan_vien.pk, ky_cong.nam, ky_cong.thang)
    return ban_chot


def du_lieu_tong_hop(nhan_vien, ky_cong):
    """Chuyển kết quả tổng hợp tháng thành các trường của bảng Tổng hợp công."""
    from .hien_thi import tong_hop_cong_thang

    dong = tong_hop_cong_thang(NhanVien.objects.filter(pk=nhan_vien.pk), ky_cong.nam, ky_cong.thang, ky_cong)[0]
    return {
        'thang': ky_cong.thang, 'nam': ky_cong.nam,
        'cong_chuan': dong['standard'] or 0, 'cong_thuc_te': dong['actual'],
        'cong_nghi_co_luong': dong['leave'], 'so_ngay_khong_phep': dong['absent'],
        'tong_cong': dong['paid'],
        'gio_tang_ca': dong['ot'], 'so_lan_tre': dong['late_count'],
        'so_phut_tre': dong['late'], 'trang_thai': dong['state'],
    }


def tong_hop_dung_tinh_luong(nhan_vien, ky_cong):
    """Đọc bản tổng hợp còn khớp nguồn; dữ liệu cũ chưa đồng bộ chỉ tính trong bộ nhớ."""
    du_lieu = du_lieu_tong_hop(nhan_vien, ky_cong)
    da_luu = TongHopCong.objects.filter(nhan_vien=nhan_vien, ky_cong=ky_cong).first()
    if da_luu and all(getattr(da_luu, khoa) == gia_tri for khoa, gia_tri in du_lieu.items()):
        return da_luu
    return TongHopCong(nhan_vien=nhan_vien, ky_cong=ky_cong, **du_lieu)


@transaction.atomic
def cap_nhat_tong_hop(nhan_vien, ky_cong):
    """Cập nhật một bản tổng hợp và nối với bản chốt còn thiếu liên kết."""
    PayrollPeriod.objects.select_for_update().get(pk=ky_cong.pk)
    tong_hop, _ = TongHopCong.objects.update_or_create(
        nhan_vien=nhan_vien, ky_cong=ky_cong, defaults=du_lieu_tong_hop(nhan_vien, ky_cong),
    )
    return tong_hop


def cap_nhat_tong_hop_ca_ky(ky_cong):
    """Đồng bộ tổng hợp của các nhân viên đã vào làm trước cuối kỳ."""
    for nhan_vien in NhanVien.objects.filter(ngay_vao_lam__lte=_ngay_cuoi_ky(ky_cong)):
        cap_nhat_tong_hop(nhan_vien, ky_cong)


def ghi_lich_su_dieu_chinh(ban_ghi, nguoi_sua, ly_do, cu, moi):
    """Chỉ ghi những trường thay đổi của bản chấm công đã tồn tại."""
    from bang_cong.forms import CAC_TRUONG_DIEU_CHINH

    if not cu:
        return
    luc_sua = timezone.now()
    LichSuDieuChinhCong.objects.bulk_create([
        LichSuDieuChinhCong(
            cham_cong=ban_ghi,
            nguoi_thuc_hien=nguoi_sua, ngay_dieu_chinh=luc_sua, ly_do=ly_do,
            truong_dieu_chinh=truong, gia_tri_cu=str(cu.get(truong, '')),
            gia_tri_moi=str(moi.get(truong, '')),
        ) for truong in CAC_TRUONG_DIEU_CHINH if cu.get(truong, '') != moi.get(truong, '')
    ])
