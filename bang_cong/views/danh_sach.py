from urllib.parse import urlencode
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from bang_cong.models import ChamCong, ChotBangCong
from bang_cong.services.chot_bang_cong_service import ChotBangCongService
from bang_cong.services.cham_cong_service import lich_thang as tao_lich_thang, nap_cong_ngay
from bang_cong.utils.date_utils import thang_lich, thang_tu_ma
from nhan_vien.access import (
    co_vai_tro, nhan_vien_duoc_hien_thi, yeu_cau_vai_tro,
    NHAN_SU, GIAM_DOC, TRUONG_PHONG,
)
from bang_cong.filters import BoLocBangCong

from .chi_tiet import bang_cong_nhan_vien

ZERO = Decimal('0')


def tong_hop_cong_thang(ds_nhan_vien, nam, thang, ky_cong, *, ds_ban_ghi=None, lich_thang=None):
    records = list(ds_ban_ghi) if ds_ban_ghi is not None else list(ChamCong.objects.filter(
        ngay__year=nam, ngay__month=thang,
        nhan_vien_id__in=ds_nhan_vien.values('pk'),
    ).select_related('nhan_vien'))
    lich = lich_thang if lich_thang is not None else tao_lich_thang(nam, thang, ky_cong)
    if ky_cong:
        nap_cong_ngay(records, ky_cong, lich)

    by_employee = {}
    for record in records:
        row = by_employee.setdefault(record.nhan_vien_id, {
            'hours': ZERO, 'overtime': ZERO, 'late': 0, 'late_count': 0,
            'incomplete': 0, 'absent': 0, 'actual': ZERO, 'leave': ZERO, 'paid': ZERO,
        })
        row['hours'] += record.so_gio_lam
        row['overtime'] += record.so_gio_tang_ca
        row['late'] += record.so_phut_tre
        row['late_count'] += record.so_phut_tre > 0
        row['incomplete'] += record.trang_thai == 'incomplete'
        row['absent'] += record.trang_thai == 'absent'
        row['actual'] += record.cong_thuc_te
        row['leave'] += record.cong_nghi_co_luong
        row['paid'] += record.tong_cong

    approved_ids = set(ChotBangCong.objects.filter(
        tong_hop__nam=nam, tong_hop__thang=thang,
    ).values_list('tong_hop__nhan_vien_id', flat=True))
    if ky_cong and ky_cong.trang_thai == 'approved':
        approved_ids.update(ds_nhan_vien.values_list('pk', flat=True))
    standard = sum((day.cong_chuan for day in lich.values()), ZERO) if lich else None

    rows = []
    for employee in ds_nhan_vien:
        row = by_employee.get(employee.pk, {})
        state = 'empty'
        if row:
            state = 'incomplete' if row['incomplete'] else 'pending'
            if employee.pk in approved_ids:
                state = 'approved'
        label = {
            'empty': 'Chưa có dữ liệu', 'approved': 'Đã duyệt',
            'pending': 'Chờ duyệt', 'incomplete': 'Cần kiểm tra',
        }[state]
        rows.append({
            'employee': employee, 'standard': standard,
            'paid': row.get('paid', ZERO), 'actual': row.get('actual', ZERO),
            'leave': row.get('leave', ZERO), 'hours': row.get('hours', ZERO),
            'overtime': row.get('overtime', ZERO), 'late': row.get('late', 0),
            'late_count': row.get('late_count', 0), 'absent': row.get('absent', 0),
            'state': state, 'state_label': label, 'has_records': bool(row),
        })
    return rows


def tham_so_phan_trang(request):
    query = request.GET.copy()
    query.pop('page', None)
    return query.urlencode()


@login_required
@require_POST
def chot_bang_cong_thang(request, period_id):
    yeu_cau_vai_tro(request.user, NHAN_SU)
    period = thang_tu_ma(period_id)
    try:
        result = ChotBangCongService.chot_bang_cong(
            period.thang, period.nam, request.user,
        )
    except ValidationError as error:
        messages.error(request, '; '.join(error.messages))
    else:
        messages.success(
            request,
            f"Đã chốt bảng công tháng {period.thang:02}/{period.nam} "
            f"cho {result['so_nhan_vien']} nhân viên.",
        )
    return redirect(reverse('bang_cong:danh-sach') + '?' + urlencode({
        'month': period.thang, 'year': period.nam,
    }))


@login_required
def danh_sach_bang_cong(request):
    if not co_vai_tro(request.user, NHAN_SU, GIAM_DOC, TRUONG_PHONG):
        nhan_vien = nhan_vien_duoc_hien_thi(request.user).first()
        if nhan_vien:
            return bang_cong_nhan_vien(request, nhan_vien.pk)

    form = BoLocBangCong(request.user, request.GET)
    rows, period = [], None
    if form.is_valid():
        data = form.cleaned_data
        employees = form.nhan_vien_trong_pham_vi(request.user)
        if data['q']:
            employees = employees.filter(
                Q(ho_va_ten__icontains=data['q']) | Q(ma_ho_so__icontains=data['q']),
            )
        period = thang_lich(data['year'], data['month'])
        if data.get('day'):
            employees = employees.filter(
                dang_hoat_dong=True, ngay_vao_lam__lte=data['day'],
            )
            attendance = ChamCong.objects.filter(ngay=data['day'], gio_vao__isnull=False)
            if data['day_state'] == 'unchecked':
                employees = employees.exclude(pk__in=attendance.values('nhan_vien_id'))
            elif data['day_state'] in ('ontime', 'late'):
                field = 'gio_vao__lte' if data['day_state'] == 'ontime' else 'gio_vao__gt'
                employees = employees.filter(
                    pk__in=attendance.filter(**{field: period.gio_bat_dau}).values('nhan_vien_id'),
                )
        rows = tong_hop_cong_thang(employees, data['year'], data['month'], period)
        if data['review']:
            rows = [row for row in rows if row['state'] == data['review']]

    page_obj = Paginator(rows, 15).get_page(request.GET.get('page'))
    return render(request, 'bang_cong/danh_sach.html', {
        'form': form, 'rows': rows, 'period': period, 'page_obj': page_obj,
        'page_query': tham_so_phan_trang(request),
        'can_edit': co_vai_tro(request.user, NHAN_SU, GIAM_DOC),
        'can_chot': co_vai_tro(request.user, NHAN_SU) and bool(period),
        'director': co_vai_tro(request.user, GIAM_DOC),
    })
