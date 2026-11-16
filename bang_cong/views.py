"""Nhận request, kiểm tra quyền và trả trang Bảng công; nghiệp vụ nằm trong services."""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from nhan_vien.access import nhan_vien_duoc_hien_thi, yeu_cau_vai_tro, co_vai_tro, NHAN_SU, GIAM_DOC, TRUONG_PHONG
from nhan_vien.models import NhanVien
from .forms import ChamCongForm, BoLocBangCong
from .models import ChamCong
from .thang_lich import thang_lich, thang_tu_ma
from .services.quy_trinh import luu_cham_cong, xu_ly_trang_thai_ky_cong, duyet_cong_nhan_vien, cham_cong_da_khoa, nam_trong_han_sua
from .services.hien_thi import tong_hop_cong_thang, du_lieu_cong_thang, du_lieu_lich_su_cong


@login_required
def danh_sach_bang_cong(request):
    if not co_vai_tro(request.user, NHAN_SU, GIAM_DOC, TRUONG_PHONG):
        nhan_vien = nhan_vien_duoc_hien_thi(request.user).first()
        if nhan_vien:
            return bang_cong_nhan_vien(request, nhan_vien.pk)
    form = BoLocBangCong(request.user, request.GET)
    danh_sach = []
    ky_cong = None
    if form.is_valid():
        du_lieu = form.cleaned_data
        ds_nhan_vien = form.nhan_vien_trong_pham_vi(request.user)
        if du_lieu['q']:
            ds_nhan_vien = ds_nhan_vien.filter(
                Q(ho_va_ten__icontains=du_lieu['q']) | Q(ma_ho_so__icontains=du_lieu['q']),
            )
        ky_cong = thang_lich(du_lieu['year'], du_lieu['month'])
        if du_lieu.get('day'):
            ds_nhan_vien = ds_nhan_vien.filter(dang_hoat_dong=True, ngay_vao_lam__lte=du_lieu['day'])
            da_cham_cong = ChamCong.objects.filter(ngay=du_lieu['day'], gio_vao__isnull=False)
            if du_lieu['day_state'] == 'unchecked':
                ds_nhan_vien = ds_nhan_vien.exclude(
                    pk__in=da_cham_cong.values_list('nhan_vien_id', flat=True),
                )
            elif du_lieu['day_state'] in ('ontime', 'late'):
                if not ky_cong:
                    ds_nhan_vien = ds_nhan_vien.none()
                else:
                    phep_so_sanh = 'gio_vao__lte' if du_lieu['day_state'] == 'ontime' else 'gio_vao__gt'
                    ds_nhan_vien = ds_nhan_vien.filter(pk__in=da_cham_cong.filter(
                        **{phep_so_sanh: ky_cong.gio_bat_dau},
                    ).values_list('nhan_vien_id', flat=True))
        danh_sach = tong_hop_cong_thang(ds_nhan_vien, du_lieu['year'], du_lieu['month'], ky_cong)
        if du_lieu['review']:
            danh_sach = [dong for dong in danh_sach if dong['state'] == du_lieu['review']]
    for dong in danh_sach:
        dong['can_approve'] = dong['state'] == 'pending'
    page_obj = Paginator(danh_sach, 15).get_page(request.GET.get('page'))
    can_bulk_approve = (
        co_vai_tro(request.user, NHAN_SU) and bool(ky_cong)
        and any(dong['can_approve'] for dong in page_obj.object_list)
    )
    return render(request, 'bang_cong/list.html', {
        'form': form, 'rows': danh_sach, 'period': ky_cong,
        'page_obj': page_obj,
        'page_query': tham_so_phan_trang(request),
        'can_edit': co_vai_tro(request.user, NHAN_SU, GIAM_DOC),
        'can_bulk_approve': can_bulk_approve,
        'director': co_vai_tro(request.user, GIAM_DOC),
    })


def tham_so_phan_trang(request):
    gia_tri = request.GET.copy()
    gia_tri.pop('page', None)
    return gia_tri.urlencode()


@login_required
def bang_cong_ca_nhan(request):
    nhan_vien = get_object_or_404(NhanVien, nguoi_dung=request.user)
    return bang_cong_nhan_vien(request, nhan_vien.pk, chi_xem_ban_than=True)


@login_required
def bang_cong_nhan_vien(request, employee_id, chi_xem_ban_than=False):
    pham_vi = NhanVien.objects.filter(nguoi_dung=request.user) if chi_xem_ban_than else nhan_vien_duoc_hien_thi(request.user)
    nhan_vien = get_object_or_404(pham_vi, pk=employee_id)
    ngu_canh = du_lieu_cong_thang(request, nhan_vien)
    la_ca_nhan = chi_xem_ban_than or not co_vai_tro(request.user, NHAN_SU, GIAM_DOC, TRUONG_PHONG)
    co_quyen_quan_ly = not la_ca_nhan and co_vai_tro(request.user, NHAN_SU, GIAM_DOC)
    ky_cong = ngu_canh['period']
    tong_hop = ngu_canh['summary']
    ky_da_duyet = ky_cong and ky_cong.trang_thai == 'approved'
    nhan_vien_da_duyet = tong_hop and tong_hop['state'] == 'approved'
    ngu_canh.update({
        'employee': nhan_vien, 'personal': la_ca_nhan,
        'can_edit': co_quyen_quan_ly and not ky_da_duyet and not nhan_vien_da_duyet,
        'can_approve': co_quyen_quan_ly,
        'page_obj': Paginator(ngu_canh['rows'], 6 if la_ca_nhan else 12).get_page(request.GET.get('page')),
        'page_query': ngu_canh['month_query'], 'director': co_vai_tro(request.user, GIAM_DOC),
        'initials': ''.join(tu[0] for tu in nhan_vien.ho_va_ten.split()[-2:]).upper(),
        'tabs': [('', 'Tất cả'), ('late', 'Đi trễ'), ('leave', 'Nghỉ phép'), ('absent', 'Nghỉ không phép')],
    })
    for item in ngu_canh['rows']:
        item['co_the_sua'] = bool(
            ngu_canh['can_edit'] and item['record'] and nam_trong_han_sua(item['date'])
        )
    return render(request, 'bang_cong/month.html', ngu_canh)


@login_required
@require_POST
def duyet_bang_cong_nhan_vien(request, employee_id, period_id):
    yeu_cau_vai_tro(request.user, NHAN_SU, GIAM_DOC)
    nhan_vien = get_object_or_404(nhan_vien_duoc_hien_thi(request.user), pk=employee_id)
    ky_cong = thang_tu_ma(period_id)
    try:
        ban_chot = duyet_cong_nhan_vien(request.user, nhan_vien, ky_cong.pk)
    except ValidationError as loi:
        messages.error(request, '; '.join(loi.messages))
    else:
        messages.success(request, f'Đã duyệt bảng công của {nhan_vien.ho_va_ten} tháng {ky_cong}.')
        if getattr(ban_chot, 'payroll_error', ''):
            messages.warning(request, 'Chưa đủ điều kiện cập nhật lương: ' + ban_chot.payroll_error)
    return redirect(reverse('bang_cong:cong-nhan-vien', args=[nhan_vien.pk]) + '?' +
                    urlencode({'month': ky_cong.thang, 'year': ky_cong.nam}))


@login_required
@require_POST
def duyet_cong_hang_loat(request, period_id):
    yeu_cau_vai_tro(request.user, NHAN_SU)
    ky_cong = thang_tu_ma(period_id)
    selected_ids = []
    for raw_id in request.POST.getlist('employee_ids'):
        try:
            employee_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if employee_id not in selected_ids:
            selected_ids.append(employee_id)

    selected = nhan_vien_duoc_hien_thi(request.user).filter(pk__in=selected_ids)
    selected_by_id = {employee.pk: employee for employee in selected}
    succeeded, failures = [], []
    for employee_id in selected_ids:
        employee = selected_by_id.get(employee_id)
        if employee is None:
            failures.append(f'Nhân viên #{employee_id}: không thuộc phạm vi được duyệt.')
            continue
        try:
            duyet_cong_nhan_vien(request.user, employee, ky_cong.pk)
        except ValidationError as error:
            failures.append(f'{employee.ho_va_ten}: ' + '; '.join(error.messages))
        else:
            succeeded.append(employee.ho_va_ten)

    if succeeded:
        messages.success(request, f'Đã duyệt công cho {len(succeeded)} nhân viên.')
    for error in failures:
        messages.error(request, error)
    if not selected_ids:
        messages.warning(request, 'Hãy chọn ít nhất một nhân viên cần duyệt.')
    return redirect(reverse('bang_cong:danh-sach') + '?' + urlencode({
        'month': ky_cong.thang, 'year': ky_cong.nam,
    }))


@login_required
def lich_su_dieu_chinh(request, employee_id):
    pham_vi = NhanVien.objects.filter(Q(pk__in=nhan_vien_duoc_hien_thi(request.user).values('pk')) | Q(nguoi_dung=request.user))
    nhan_vien = get_object_or_404(pham_vi, pk=employee_id)
    ngu_canh = du_lieu_lich_su_cong(request, nhan_vien)
    ngu_canh.update({
        'employee': nhan_vien,
        'page_obj': Paginator(ngu_canh['rows'], 20).get_page(request.GET.get('page')),
        'page_query': tham_so_phan_trang(request),
    })
    return render(request, 'bang_cong/history.html', ngu_canh)


@login_required
def sua_cham_cong(request, pk=None):
    yeu_cau_vai_tro(request.user, NHAN_SU, GIAM_DOC)
    dong = get_object_or_404(ChamCong, pk=pk, nhan_vien__in=nhan_vien_duoc_hien_thi(request.user)) if pk else None
    if dong and cham_cong_da_khoa(dong):
        raise PermissionDenied('Bảng công đã duyệt, không được chỉnh sửa.')
    if dong and not nam_trong_han_sua(dong.ngay):
        raise PermissionDenied('Chỉ được sửa bảng công trong vòng 7 ngày gần nhất.')
    ban_dau = {'employee': request.GET.get('employee'), 'date': request.GET.get('date')} if not dong else None
    form = ChamCongForm(request.user, request.POST or None, instance=dong, initial=ban_dau)
    if request.method == 'POST' and form.is_valid():
        try:
            da_luu = luu_cham_cong(request.user, form.save(commit=False), form.cleaned_data['reason'])
        except ValidationError as loi:
            form.add_error(None, '; '.join(loi.messages))
        except IntegrityError:
            form.add_error(None, 'Đã có bản ghi nhân viên/ngày này hoặc dữ liệu không hợp lệ.')
        else:
            messages.success(request, 'Đã lưu và tính lại công.')
            return redirect(reverse('bang_cong:cong-nhan-vien', args=[da_luu.nhan_vien_id]) + '?' +
                            urlencode({'month': da_luu.ngay.month, 'year': da_luu.ngay.year}))
    return render(request, 'bang_cong/edit.html', {'form': form, 'title': 'Ghi nhận / chỉnh sửa chấm công', 'row': dong})


@login_required
@require_POST
def doi_trang_thai_ky_cong(request, pk):
    yeu_cau_vai_tro(request.user, GIAM_DOC)
    ky_cong = thang_tu_ma(pk)
    try:
        xu_ly_trang_thai_ky_cong(request.user, pk, request.POST.get('action'), request.POST.get('reason', ''))
    except ValidationError as loi:
        messages.error(request, '; '.join(loi.messages))
    else:
        messages.success(request, 'Đã cập nhật trạng thái kỳ công.')
    return redirect(reverse('bang_cong:danh-sach') + '?' + urlencode({'month': ky_cong.thang, 'year': ky_cong.nam}))
