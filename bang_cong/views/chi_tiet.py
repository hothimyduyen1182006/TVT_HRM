import calendar
from datetime import date
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from bang_cong.models import ChamCong
from bang_cong.services.cham_cong_service import (
    nap_cong_ngay, tinh_tang_ca_tu_dong,
)
from nhan_vien.access import (
    co_vai_tro, nhan_vien_duoc_hien_thi, NHAN_SU, GIAM_DOC, TRUONG_PHONG,
)
from nhan_vien.models import NhanVien

ZERO = Decimal('0')
WEEKDAYS = ('T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN')


def _danh_sach_cong_ngay(nhan_vien, nam, thang, records, tang_ca):
    by_day = {record.ngay: record for record in records}
    today = timezone.localdate()
    last_day = calendar.monthrange(nam, thang)[1]
    if (nam, thang) == (today.year, today.month):
        last_day = min(last_day, today.day)

    rows = []
    for number in range(last_day, 0, -1):
        ngay = date(nam, thang, number)
        if ngay < nhan_vien.ngay_vao_lam:
            continue
        record = by_day.get(ngay)
        state, label = 'incomplete', 'Chưa có dữ liệu'
        if record:
            state, label = {
                'present': ('late', 'Đi làm trễ') if record.so_phut_tre else ('present', 'Đi đúng giờ'),
                'leave': ('leave', 'Nghỉ có lương' if record.cong_nghi_co_luong else 'Nghỉ không lương'),
                'absent': ('absent', 'Nghỉ không phép'),
            }.get(record.trang_thai, ('incomplete', 'Thiếu dữ liệu'))
        ot = tang_ca.get(record.pk, {}) if record else {}
        rows.append({
            'date': ngay, 'weekday': WEEKDAYS[ngay.weekday()], 'record': record,
            'state': state, 'label': label, 'ot': ot.get('hours', ZERO),
            'ot_error': ot.get('error', ''), 'ot_warnings': ot.get('warnings', []),
        })
    return rows


def _du_lieu_cong_thang(request, nhan_vien):
    today = timezone.localdate()
    try:
        month = int(request.GET.get('thang', today.month))
        year = int(request.GET.get('nam', today.year))
    except (TypeError, ValueError):
        month, year = today.month, today.year
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        month, year = today.month, today.year

    records = list(ChamCong.objects.filter(
        nhan_vien=nhan_vien, ngay__year=year, ngay__month=month,
    ).select_related('nhan_vien'))
    if records:
        nap_cong_ngay(records, year, month)
    overtime = {
        record.pk: tinh_tang_ca_tu_dong(record)
        for record in records
    }
    from .danh_sach import tong_hop_cong_thang

    summary = tong_hop_cong_thang(
        NhanVien.objects.filter(pk=nhan_vien.pk), year, month,
        ds_ban_ghi=records,
    )[0]
    rows = _danh_sach_cong_ngay(nhan_vien, year, month, records, overtime)
    days = sum(bool(row['record'] and row['record'].gio_vao) for row in rows)
    average = '—'
    if days:
        minutes = int(summary['hours'] * 60 / days)
        average = f'{minutes // 60}:{minutes % 60:02}'
    progress = 0
    if summary['standard']:
        progress = max(0, min(100, int(summary['paid'] / summary['standard'] * 100)))

    return {
        'month': month, 'year': year, 'rows': rows, 'summary': summary,
        'period': True, 'progress': progress, 'average': average,
        'month_query': urlencode({'thang': month, 'nam': year}),
    }


@login_required
def bang_cong_nhan_vien(request, employee_id, chi_xem_ban_than=False):
    pham_vi = (
        NhanVien.objects.filter(nguoi_dung=request.user)
        if chi_xem_ban_than else nhan_vien_duoc_hien_thi(request.user)
    )
    nhan_vien = get_object_or_404(pham_vi, pk=employee_id)
    context = _du_lieu_cong_thang(request, nhan_vien)
    personal = chi_xem_ban_than or not co_vai_tro(
        request.user, NHAN_SU, GIAM_DOC, TRUONG_PHONG,
    )
    context.update({
        'employee': nhan_vien,
        'personal': personal,
        'page_obj': Paginator(context['rows'], 6 if personal else 12).get_page(
            request.GET.get('page'),
        ),
        'page_query': context['month_query'],
        'director': co_vai_tro(request.user, GIAM_DOC),
        'initials': ''.join(part[0] for part in nhan_vien.ho_va_ten.split()[-2:]).upper(),
        'tabs': [('', 'Tất cả'), ('late', 'Đi trễ'), ('leave', 'Nghỉ phép'),
                 ('absent', 'Nghỉ không phép')],
    })
    template = 'bang_cong/ca_nhan.html' if personal else 'bang_cong/chi_tiet.html'
    return render(request, template, context)
