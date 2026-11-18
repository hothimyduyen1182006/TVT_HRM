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
from bang_cong.services.chot_bang_cong_service import ChotBangCongService, ky_cong_da_khoa
from bang_cong.services.cham_cong_service import (
    GIO_BAT_DAU, cong_chuan_thang, nap_cong_ngay,
)
from nhan_vien.access import (
    co_vai_tro, nhan_vien_duoc_hien_thi, yeu_cau_vai_tro,
    NHAN_SU, GIAM_DOC, TRUONG_PHONG,
)
from bang_cong.filters import BoLocBangCong

from .chi_tiet import bang_cong_nhan_vien

ZERO = Decimal('0')


def tong_hop_cong_thang(ds_nhan_vien, nam, thang, *, ds_ban_ghi=None):
    records = list(ds_ban_ghi) if ds_ban_ghi is not None else list(ChamCong.objects.filter(
        ngay__year=nam, ngay__month=thang,
        nhan_vien_id__in=ds_nhan_vien.values('pk'),
    ).select_related('nhan_vien'))
    if records:
        nap_cong_ngay(records, nam, thang)

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
    if ky_cong_da_khoa(nam, thang):
        approved_ids.update(ds_nhan_vien.values_list('pk', flat=True))
    standard = cong_chuan_thang(nam, thang)

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
    period_id = int(period_id)
    nam, thang = period_id // 100, period_id % 100
    try:
        result = ChotBangCongService.chot_bang_cong(
            thang, nam, request.user,
        )
    except ValidationError as error:
        messages.error(request, '; '.join(error.messages))
    else:
        messages.success(
            request,
            f"Đã chốt bảng công tháng {thang:02}/{nam} "
            f"cho {result['so_nhan_vien']} nhân viên.",
        )
    return redirect(reverse('bang_cong:danh-sach') + '?' + urlencode({
        'month': thang, 'year': nam,
    }))


@login_required
def danh_sach_bang_cong(request):
    if not co_vai_tro(request.user, NHAN_SU, GIAM_DOC, TRUONG_PHONG):
        nhan_vien = nhan_vien_duoc_hien_thi(request.user).first()
        if nhan_vien:
            return bang_cong_nhan_vien(request, nhan_vien.pk)

    form = BoLocBangCong(request.user, request.GET)
    rows, period, period_id = [], False, None
    if form.is_valid():
        data = form.cleaned_data
        employees = form.nhan_vien_trong_pham_vi(request.user)
        if data['q']:
            employees = employees.filter(
                Q(ho_va_ten__icontains=data['q']) | Q(ma_ho_so__icontains=data['q']),
            )
        nam, thang = data['year'], data['month']
        ma_ky_cong = nam * 100 + thang
        period = True
        period_id = ma_ky_cong
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
                    pk__in=attendance.filter(**{field: GIO_BAT_DAU}).values('nhan_vien_id'),
                )
        rows = tong_hop_cong_thang(employees, nam, thang)
        if data['review']:
            rows = [row for row in rows if row['state'] == data['review']]

    page_obj = Paginator(rows, 15).get_page(request.GET.get('page'))
    return render(request, 'bang_cong/danh_sach.html', {
        'form': form, 'rows': rows, 'period': period,
        'period_id': period_id, 'page_obj': page_obj,
        'page_query': tham_so_phan_trang(request),
        'can_edit': co_vai_tro(request.user, NHAN_SU, GIAM_DOC),
        'can_chot': co_vai_tro(request.user, NHAN_SU) and period,
        'director': co_vai_tro(request.user, GIAM_DOC),
    })
