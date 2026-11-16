"""Chốt toàn bộ bảng công đã tổng hợp của một tháng."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from bang_cong.models import ChotBangCong, TongHopCong
from nhan_vien.access import NHAN_SU, yeu_cau_vai_tro


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
