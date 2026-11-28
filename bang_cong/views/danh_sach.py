from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from bang_cong.filters import BoLocBangCong
from bang_cong.services.chot_bang_cong_service import duyet_cong_nhan_vien
from bang_cong.services.tong_hop_service import tong_hop_theo_nhan_vien
from config.dashboard import loc_nhan_vien_theo_cham_cong
from nhan_vien.access import (
    co_vai_tro, nhan_vien_duoc_hien_thi, yeu_cau_vai_tro,
    NHAN_SU, GIAM_DOC, TRUONG_PHONG,
)

from .chi_tiet import bang_cong_nhan_vien


@login_required
def danh_sach_bang_cong(request):
    if not co_vai_tro(request.user, NHAN_SU, GIAM_DOC, TRUONG_PHONG):
        nhan_vien = nhan_vien_duoc_hien_thi(request.user).first()
        if nhan_vien:
            return bang_cong_nhan_vien(request, nhan_vien.pk)

    form = BoLocBangCong(request.user, request.GET)
    rows, period_id, month_query = [], None, ''
    if form.is_valid():
        data = form.cleaned_data
        employees = form.nhan_vien_trong_pham_vi(request.user)
        tu_khoa = data['tu_khoa']
        if tu_khoa:
            employees = employees.filter(
                Q(ho_va_ten__icontains=tu_khoa) | Q(ma_ho_so__icontains=tu_khoa),
            )
        nam, thang = data['nam'], data['thang']
        period_id = nam * 100 + thang
        month_query = urlencode({'thang': thang, 'nam': nam})
        ngay_cham_cong = data['ngay_cham_cong']
        if ngay_cham_cong:
            employees = loc_nhan_vien_theo_cham_cong(
                employees, ngay_cham_cong, data['trang_thai_cham_cong'],
            )
        rows = tong_hop_theo_nhan_vien(employees, nam, thang)
        if data['trang_thai']:
            rows = [row for row in rows if row['trang_thai'] == data['trang_thai']]

    return render(request, 'bang_cong/danh_sach.html', {
        'form': form, 'rows': rows, 'month_query': month_query,
        'period_id': period_id,
        'can_chot': period_id is not None and co_vai_tro(request.user, NHAN_SU),
    })


@login_required
@require_POST
def chot_nhan_vien_da_chon(request, period_id):
    yeu_cau_vai_tro(request.user, NHAN_SU)
    nam, thang = divmod(period_id, 100)
    try:
        if not (2020 <= nam <= 2030 and 1 <= thang <= 12):
            raise ValidationError('Kỳ công không hợp lệ.')
        truong_nhan_vien = forms.ModelMultipleChoiceField(
            queryset=nhan_vien_duoc_hien_thi(request.user),
            error_messages={
                'required': 'Cần chọn ít nhất một nhân viên để chốt.',
                'invalid_choice': 'Danh sách có nhân viên không hợp lệ hoặc ngoài phạm vi quyền.',
                'invalid_pk_value': 'Mã nhân viên không hợp lệ.',
            },
        )
        danh_sach = truong_nhan_vien.clean(request.POST.getlist('nhan_vien'))
        with transaction.atomic():
            ds_nhan_vien = list(danh_sach.order_by('pk'))
            for nhan_vien in ds_nhan_vien:
                duyet_cong_nhan_vien(request.user, nhan_vien, period_id)
    except ValidationError as error:
        messages.error(request, '; '.join(error.messages))
    else:
        messages.success(
            request,
            f"Đã chốt bảng công tháng {thang:02}/{nam} "
            f"cho {len(ds_nhan_vien)} nhân viên.",
        )
    return redirect(reverse('bang_cong:danh-sach') + '?' + urlencode({
        'thang': thang, 'nam': nam,
    }))
