"""Chốt bảng công và xử lý quy trình duyệt công."""

import calendar
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from bang_cong.models import ChamCong, ChotBangCong, TongHopCong
from nhan_vien.access import GIAM_DOC, NHAN_SU, yeu_cau_vai_tro
from nhan_vien.models import NhanVien


def _ngay_cuoi_ky(nam, thang):
    return date(nam, thang, calendar.monthrange(nam, thang)[1])


def _tinh_lai_cac_ban_ghi(ds_ban_ghi, nguoi_thuc_hien, ly_do):
    """Tính lại công cho các bản ghi trước khi duyệt kỳ hoặc nhân viên."""
    from .cham_cong_service import tinh_cong_ngay

    for ban_ghi in ds_ban_ghi:
        tinh_cong_ngay(ban_ghi)
        ban_ghi.save()


class ChotBangCongService:
    @staticmethod
    @transaction.atomic
    def chot_bang_cong(thang, nam, nguoi_chot):
        yeu_cau_vai_tro(nguoi_chot, NHAN_SU)
        bang_cong = list(
            TongHopCong.objects.select_for_update()
            .filter(thang=thang, nam=nam)
            .order_by('pk')
        )
        if not bang_cong:
            raise ValidationError('Chưa có dữ liệu tổng hợp công để chốt.')

        ids = [cong.pk for cong in bang_cong]
        if (ChotBangCong.objects.filter(tong_hop_id__in=ids).exists()
                or any(cong.trang_thai == 'approved' for cong in bang_cong)):
            raise ValidationError('Bảng công tháng này đã được chốt.')

        thoi_diem_chot = timezone.now()
        ChotBangCong.objects.bulk_create([
            ChotBangCong(
                tong_hop_id=cong.pk,
                nguoi_duyet=nguoi_chot,
                ngay_duyet=thoi_diem_chot,
            )
            for cong in bang_cong
        ])
        TongHopCong.objects.filter(pk__in=ids).update(trang_thai='approved')

        return {
            'thang': thang,
            'nam': nam,
            'so_nhan_vien': len(bang_cong),
            'nguoi_chot': nguoi_chot.pk,
            'ngay_chot': thoi_diem_chot,
            'trang_thai': 'approved',
        }


def ky_cong_da_khoa(nam, thang, ma_nhan_vien=None):
    """Kiểm tra tháng đã chốt toàn bộ hoặc đã chốt cho một nhân viên."""
    ngay_cuoi = _ngay_cuoi_ky(nam, thang)
    nhan_vien_can_duyet = set(NhanVien.objects.filter(
        dang_hoat_dong=True,
        ngay_vao_lam__lte=ngay_cuoi,
    ).values_list('pk', flat=True))
    nhan_vien_da_duyet = set(ChotBangCong.objects.filter(
        tong_hop__nam=nam,
        tong_hop__thang=thang,
    ).values_list('tong_hop__nhan_vien_id', flat=True))

    if nhan_vien_can_duyet and nhan_vien_can_duyet.issubset(nhan_vien_da_duyet):
        return True
    if ma_nhan_vien is None:
        return False
    return ma_nhan_vien in nhan_vien_da_duyet


@transaction.atomic
def xu_ly_trang_thai_ky_cong(nguoi_thuc_hien, ma_ky_cong, thao_tac, ly_do):
    """Duyệt toàn bộ kỳ công sau khi kiểm tra các ngày làm việc bắt buộc."""
    yeu_cau_vai_tro(nguoi_thuc_hien, GIAM_DOC)
    if thao_tac != 'approve':
        raise ValidationError('Chỉ được duyệt công; bảng công đã duyệt không được mở lại.')
    ma_ky_cong = int(ma_ky_cong)
    nam, thang = ma_ky_cong // 100, ma_ky_cong % 100
    if not ly_do.strip():
        raise ValidationError('Cần ghi lý do.')
    if ky_cong_da_khoa(nam, thang):
        raise ValidationError('Kỳ công phải đang chờ duyệt.')

    from .cham_cong_service import kiem_tra_lich_lam_viec
    from .tong_hop_service import cap_nhat_tong_hop, cap_nhat_tong_hop_ca_ky

    lich_da_kiem_tra = kiem_tra_lich_lam_viec(nam, thang)
    ds_ban_ghi = ChamCong.objects.filter(ngay__year=nam, ngay__month=thang)
    ds_nhan_vien = NhanVien.objects.filter(
        dang_hoat_dong=True, ngay_vao_lam__lte=_ngay_cuoi_ky(nam, thang),
    )
    for nhan_vien in ds_nhan_vien:
        ngay_bat_buoc = {
            lich_ngay.ngay for lich_ngay in lich_da_kiem_tra
            if lich_ngay.loai_ngay == 'work' and lich_ngay.ngay >= nhan_vien.ngay_vao_lam
        }
        ngay_da_co = set(
            ds_ban_ghi.filter(nhan_vien=nhan_vien)
            .exclude(trang_thai='incomplete').values_list('ngay', flat=True)
        )
        if not set(ngay_bat_buoc).issubset(ngay_da_co):
            raise ValidationError(f'{nhan_vien}: còn ngày làm việc chưa kiểm tra.')

    da_duyet_ids = ChotBangCong.objects.filter(
        tong_hop__nam=nam, tong_hop__thang=thang,
    ).values_list('tong_hop__nhan_vien_id', flat=True)
    _tinh_lai_cac_ban_ghi(
        ds_ban_ghi.exclude(nhan_vien_id__in=da_duyet_ids), nguoi_thuc_hien, ly_do,
    )
    for nhan_vien in ds_nhan_vien:
        tong_hop = cap_nhat_tong_hop(nhan_vien, nam, thang)
        ChotBangCong.objects.get_or_create(
            tong_hop=tong_hop, defaults={'nguoi_duyet': nguoi_thuc_hien},
        )

    cap_nhat_tong_hop_ca_ky(nam, thang)
    from thuong.services.quy_trinh import dong_bo_thuong_tu_dong
    from bang_luong.services.tinh_luong_service import cap_nhat_luong_nhan_vien

    ds_nhan_vien_da_chot = ChotBangCong.objects.filter(
        tong_hop__nam=nam, tong_hop__thang=thang,
    ).values_list('tong_hop__nhan_vien_id', flat=True)
    for ma_nhan_vien in ds_nhan_vien_da_chot:
        nhan_vien = NhanVien.objects.get(pk=ma_nhan_vien)
        dong_bo_thuong_tu_dong(nhan_vien, thang, nam)
        cap_nhat_luong_nhan_vien(nguoi_thuc_hien, ma_nhan_vien, nam, thang)


@transaction.atomic
def duyet_cong_nhan_vien(nguoi_thuc_hien, nhan_vien, ma_ky_cong):
    """Kiểm tra và duyệt bảng công của một nhân viên trong kỳ."""
    yeu_cau_vai_tro(nguoi_thuc_hien, NHAN_SU, GIAM_DOC)
    ma_ky_cong = int(ma_ky_cong)
    nam, thang = ma_ky_cong // 100, ma_ky_cong % 100
    if ky_cong_da_khoa(nam, thang, nhan_vien.pk):
        raise ValidationError('Bảng công nhân viên này đã được duyệt.')

    from .cham_cong_service import kiem_tra_lich_lam_viec
    from .tong_hop_service import cap_nhat_tong_hop

    lich_da_kiem_tra = kiem_tra_lich_lam_viec(nam, thang)
    ds_ban_ghi = ChamCong.objects.filter(
        nhan_vien=nhan_vien, ngay__year=nam, ngay__month=thang,
    )
    ngay_bat_buoc = {
        lich_ngay.ngay for lich_ngay in lich_da_kiem_tra
        if lich_ngay.loai_ngay == 'work' and lich_ngay.ngay >= nhan_vien.ngay_vao_lam
    }
    ngay_da_co = set(ds_ban_ghi.exclude(trang_thai='incomplete').values_list('ngay', flat=True))
    if (not ds_ban_ghi.exists() or not ngay_bat_buoc.issubset(ngay_da_co)
            or ds_ban_ghi.filter(trang_thai='incomplete').exists()):
        raise ValidationError('Bảng công nhân viên còn thiếu ngày hoặc có dữ liệu chưa kiểm tra.')

    _tinh_lai_cac_ban_ghi(ds_ban_ghi, nguoi_thuc_hien, 'Tính lại trước khi duyệt nhân viên')
    ban_chot = ChotBangCong.objects.filter(
        tong_hop__nam=nam, tong_hop__thang=thang,
        tong_hop__nhan_vien=nhan_vien,
    ).first()
    if ban_chot:
        ban_chot.nguoi_duyet = nguoi_thuc_hien
        ban_chot.ngay_duyet = timezone.now()
        ban_chot.save(update_fields=['nguoi_duyet', 'ngay_duyet'])
    else:
        ban_chot = ChotBangCong.objects.create(
            tong_hop=cap_nhat_tong_hop(nhan_vien, nam, thang), nguoi_duyet=nguoi_thuc_hien,
        )

    cap_nhat_tong_hop(nhan_vien, nam, thang)
    from bang_luong.services.tinh_luong_service import cap_nhat_luong_nhan_vien
    from thuong.services.quy_trinh import dong_bo_thuong_tu_dong

    dong_bo_thuong_tu_dong(nhan_vien, thang, nam)
    ban_chot.payroll_error = cap_nhat_luong_nhan_vien(
        nguoi_thuc_hien, nhan_vien.pk, nam, thang,
    )
    return ban_chot
