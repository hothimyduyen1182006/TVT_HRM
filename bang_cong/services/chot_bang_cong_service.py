"""Chốt bảng công và xử lý quy trình duyệt công."""

import calendar
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from bang_cong.models import ChamCong, ChotBangCong, TongHopCong
from bang_cong.thang_lich import thang_tu_ma
from nhan_vien.access import GIAM_DOC, NHAN_SU, yeu_cau_vai_tro
from nhan_vien.models import NhanVien


def _ngay_cuoi_ky(ky_cong):
    return date(ky_cong.nam, ky_cong.thang, calendar.monthrange(ky_cong.nam, ky_cong.thang)[1])


def _tinh_lai_cac_ban_ghi(ds_ban_ghi, ky_cong, nguoi_thuc_hien, ly_do):
    """Tính lại công cho các bản ghi trước khi duyệt kỳ hoặc nhân viên."""
    from .cham_cong_service import tinh_cong_ngay

    for ban_ghi in ds_ban_ghi:
        tinh_cong_ngay(ban_ghi, ky_cong)
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


def ky_cong_da_khoa(ky_cong, ma_nhan_vien, ngay_cong=None):
    """Kiểm tra kỳ đã chốt toàn bộ hoặc riêng bản tổng hợp nhân viên."""
    if not ky_cong:
        return False
    if ky_cong.trang_thai == 'approved':
        return True
    return ky_cong.employee_approvals.filter(
        tong_hop__nhan_vien_id=ma_nhan_vien,
    ).exists()


@transaction.atomic
def xu_ly_trang_thai_ky_cong(nguoi_thuc_hien, ma_ky_cong, thao_tac, ly_do):
    """Duyệt toàn bộ kỳ công sau khi kiểm tra các ngày làm việc bắt buộc."""
    yeu_cau_vai_tro(nguoi_thuc_hien, GIAM_DOC)
    if thao_tac != 'approve':
        raise ValidationError('Chỉ được duyệt công; bảng công đã duyệt không được mở lại.')
    ky_cong = thang_tu_ma(ma_ky_cong)
    if not ly_do.strip():
        raise ValidationError('Cần ghi lý do.')
    if ky_cong.trang_thai != 'pending':
        raise ValidationError('Kỳ công phải đang chờ duyệt.')

    from .cham_cong_service import kiem_tra_lich_lam_viec
    from .tong_hop_service import cap_nhat_tong_hop, cap_nhat_tong_hop_ca_ky

    lich_da_kiem_tra = kiem_tra_lich_lam_viec(ky_cong)
    ds_ban_ghi = ChamCong.objects.filter(ngay__year=ky_cong.nam, ngay__month=ky_cong.thang)
    ds_nhan_vien = NhanVien.objects.filter(
        dang_hoat_dong=True, ngay_vao_lam__lte=_ngay_cuoi_ky(ky_cong),
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

    da_duyet_ids = ky_cong.employee_approvals.values_list('tong_hop__nhan_vien_id', flat=True)
    _tinh_lai_cac_ban_ghi(
        ds_ban_ghi.exclude(nhan_vien_id__in=da_duyet_ids), ky_cong, nguoi_thuc_hien, ly_do,
    )
    for nhan_vien in ds_nhan_vien:
        tong_hop = cap_nhat_tong_hop(nhan_vien, ky_cong)
        ChotBangCong.objects.get_or_create(
            tong_hop=tong_hop, defaults={'nguoi_duyet': nguoi_thuc_hien},
        )

    cap_nhat_tong_hop_ca_ky(ky_cong)
    from thuong.services.quy_trinh import dong_bo_thuong_tu_dong
    from bang_luong.services.tinh_luong_service import cap_nhat_luong_nhan_vien

    for ma_nhan_vien in ky_cong.ds_nhan_vien:
        nhan_vien = NhanVien.objects.get(pk=ma_nhan_vien)
        dong_bo_thuong_tu_dong(nhan_vien, ky_cong.thang, ky_cong.nam)
        cap_nhat_luong_nhan_vien(nguoi_thuc_hien, ma_nhan_vien, ky_cong.nam, ky_cong.thang)


@transaction.atomic
def duyet_cong_nhan_vien(nguoi_thuc_hien, nhan_vien, ma_ky_cong):
    """Kiểm tra và duyệt bảng công của một nhân viên trong kỳ."""
    yeu_cau_vai_tro(nguoi_thuc_hien, NHAN_SU, GIAM_DOC)
    ky_cong = thang_tu_ma(ma_ky_cong)
    if ky_cong_da_khoa(ky_cong, nhan_vien.pk):
        raise ValidationError('Bảng công nhân viên này đã được duyệt.')

    from .cham_cong_service import kiem_tra_lich_lam_viec
    from .tong_hop_service import cap_nhat_tong_hop

    lich_da_kiem_tra = kiem_tra_lich_lam_viec(ky_cong)
    ds_ban_ghi = ChamCong.objects.filter(
        nhan_vien=nhan_vien, ngay__year=ky_cong.nam, ngay__month=ky_cong.thang,
    )
    ngay_bat_buoc = {
        lich_ngay.ngay for lich_ngay in lich_da_kiem_tra
        if lich_ngay.loai_ngay == 'work' and lich_ngay.ngay >= nhan_vien.ngay_vao_lam
    }
    ngay_da_co = set(ds_ban_ghi.exclude(trang_thai='incomplete').values_list('ngay', flat=True))
    if (not ds_ban_ghi.exists() or not ngay_bat_buoc.issubset(ngay_da_co)
            or ds_ban_ghi.filter(trang_thai='incomplete').exists()):
        raise ValidationError('Bảng công nhân viên còn thiếu ngày hoặc có dữ liệu chưa kiểm tra.')

    _tinh_lai_cac_ban_ghi(ds_ban_ghi, ky_cong, nguoi_thuc_hien, 'Tính lại trước khi duyệt nhân viên')
    ban_chot = ky_cong.employee_approvals.filter(tong_hop__nhan_vien=nhan_vien).first()
    if ban_chot:
        ban_chot.nguoi_duyet = nguoi_thuc_hien
        ban_chot.ngay_duyet = timezone.now()
        ban_chot.save(update_fields=['nguoi_duyet', 'ngay_duyet'])
    else:
        ban_chot = ChotBangCong.objects.create(
            tong_hop=cap_nhat_tong_hop(nhan_vien, ky_cong), nguoi_duyet=nguoi_thuc_hien,
        )

    cap_nhat_tong_hop(nhan_vien, ky_cong)
    from bang_luong.services.tinh_luong_service import cap_nhat_luong_nhan_vien
    from thuong.services.quy_trinh import dong_bo_thuong_tu_dong

    dong_bo_thuong_tu_dong(nhan_vien, ky_cong.thang, ky_cong.nam)
    ban_chot.payroll_error = cap_nhat_luong_nhan_vien(
        nguoi_thuc_hien, nhan_vien.pk, ky_cong.nam, ky_cong.thang,
    )
    return ban_chot
