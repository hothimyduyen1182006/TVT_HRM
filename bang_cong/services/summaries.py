"""Đồng bộ bảng tổng hợp và lịch sử chi tiết, dùng lại công thức công hiện có."""
import calendar
from datetime import date

from django.db import transaction

from bang_cong.models import (
    LichSuDieuChinhCong, KyCong, ChamCong,
    ChotBangCong, TongHopCong,
)
from nhan_vien.models import Employee


def summary_values(employee, period):
    from .presentation import month_summary

    row = month_summary(Employee.objects.filter(pk=employee.pk), period.nam, period.thang, period)[0]
    return {
        'thang': period.thang, 'nam': period.nam,
        'cong_chuan': row['standard'] or 0, 'cong_thuc_te': row['actual'],
        'cong_nghi_co_luong': row['leave'], 'so_ngay_khong_phep': row['absent'],
        'tong_cong': row['paid'], 'so_gio_lam': row['hours'],
        'gio_tang_ca': row['ot'], 'so_lan_tre': row['late_count'],
        'so_phut_tre': row['late'], 'trang_thai': row['state'],
    }


def payroll_summary(employee, period):
    """Đọc bản tổng hợp còn khớp nguồn; dữ liệu cũ chưa đồng bộ chỉ tính trong bộ nhớ."""
    values = summary_values(employee, period)
    saved = TongHopCong.objects.filter(nhan_vien=employee, ky_cong=period).first()
    if saved and all(getattr(saved, key) == value for key, value in values.items()):
        return saved
    return TongHopCong(nhan_vien=employee, ky_cong=period, **values)


@transaction.atomic
def refresh_summary(employee, period):
    KyCong.objects.select_for_update().get(pk=period.pk)
    summary, _ = TongHopCong.objects.update_or_create(
        nhan_vien=employee, ky_cong=period, defaults=summary_values(employee, period),
    )
    ChotBangCong.objects.filter(
        nhan_vien=employee, ky_cong=period, tong_hop__isnull=True,
    ).update(tong_hop=summary)
    return summary


def refresh_period_summaries(period):
    last_day = date(period.nam, period.thang, calendar.monthrange(period.nam, period.thang)[1])
    for employee in Employee.objects.filter(hire_date__lte=last_day):
        refresh_summary(employee, period)


def record_adjustments(audit):
    from bang_cong.forms import AUDIT_FIELDS

    if not audit.du_lieu_cu or audit.hanh_dong not in ('edit_record', 'save_record', 'recalculate'):
        return
    try:
        record_id = int(audit.du_lieu_moi.get('pk'))
    except (TypeError, ValueError):
        record_id = None
    record_id = ChamCong.objects.filter(pk=record_id).values_list('pk', flat=True).first()
    for field in AUDIT_FIELDS:
        old, new = audit.du_lieu_cu.get(field, ''), audit.du_lieu_moi.get(field, '')
        if old != new:
            LichSuDieuChinhCong.objects.get_or_create(nhat_ky=audit, truong_dieu_chinh=field, defaults={
                'cham_cong_id': record_id, 'nguoi_thuc_hien_id': audit.nguoi_thuc_hien_id,
                'gia_tri_cu': str(old), 'gia_tri_moi': str(new),
                'ly_do': audit.ly_do, 'ngay_dieu_chinh': audit.ngay_tao,
            })
