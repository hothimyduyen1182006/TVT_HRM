"""Nhận request, kiểm tra quyền và trả trang Bảng công; nghiệp vụ nằm trong services."""

import csv
import io
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from nhan_vien.access import visible_employees, require_role, has_role, HR, DIRECTOR, MANAGER
from nhan_vien.models import Employee
from .forms import ChamCongForm, BoLocBangCong
from .models import ChamCong, KyCong
from .services.quy_trinh import luu_cham_cong, xu_ly_trang_thai_ky_cong, duyet_cong_nhan_vien, cham_cong_da_khoa
from .services.hien_thi import tong_hop_cong_thang, du_lieu_cong_thang, du_lieu_lich_su_cong, du_lieu_tang_ca


@login_required
def danh_sach_bang_cong(request):
    if not has_role(request.user, HR, DIRECTOR, MANAGER):
        nhan_vien = visible_employees(request.user).first()
        if nhan_vien:
            return bang_cong_nhan_vien(request, nhan_vien.pk)
    form = BoLocBangCong(request.user, request.GET)
    danh_sach = []
    ky_cong = None
    if form.is_valid():
        du_lieu = form.cleaned_data
        ds_nhan_vien = form.employee_scope(request.user)
        if du_lieu['q']:
            ds_nhan_vien = ds_nhan_vien.filter(
                Q(full_name__icontains=du_lieu['q']) | Q(code__icontains=du_lieu['q']),
            )
        ky_cong = KyCong.objects.filter(nam=du_lieu['year'], thang=du_lieu['month']).first()
        if du_lieu.get('day'):
            ds_nhan_vien = ds_nhan_vien.filter(is_active=True, hire_date__lte=du_lieu['day'])
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
    return render(request, 'attendance/list.html', {
        'form': form, 'rows': danh_sach, 'period': ky_cong,
        'page_obj': Paginator(danh_sach, 15).get_page(request.GET.get('page')),
        'page_query': tham_so_phan_trang(request),
        'can_edit': has_role(request.user, HR, DIRECTOR),
        'director': has_role(request.user, DIRECTOR),
    })


def tham_so_phan_trang(request):
    gia_tri = request.GET.copy()
    gia_tri.pop('page', None)
    return gia_tri.urlencode()


@login_required
def bang_cong_ca_nhan(request):
    nhan_vien = get_object_or_404(Employee, user=request.user)
    return bang_cong_nhan_vien(request, nhan_vien.pk, chi_xem_ban_than=True)


@login_required
def bang_cong_nhan_vien(request, employee_id, chi_xem_ban_than=False):
    pham_vi = Employee.objects.filter(user=request.user) if chi_xem_ban_than else visible_employees(request.user)
    nhan_vien = get_object_or_404(pham_vi, pk=employee_id)
    ngu_canh = du_lieu_cong_thang(request, nhan_vien)
    la_ca_nhan = chi_xem_ban_than or not has_role(request.user, HR, DIRECTOR, MANAGER)
    co_quyen_quan_ly = not la_ca_nhan and has_role(request.user, HR, DIRECTOR)
    ky_cong = ngu_canh['period']
    tong_hop = ngu_canh['summary']
    ky_da_duyet = ky_cong and ky_cong.trang_thai == 'approved'
    nhan_vien_da_duyet = tong_hop and tong_hop['state'] == 'approved'
    ngu_canh.update({
        'employee': nhan_vien, 'personal': la_ca_nhan,
        'can_edit': co_quyen_quan_ly and not ky_da_duyet and not nhan_vien_da_duyet,
        'can_approve': co_quyen_quan_ly,
        'can_export': co_quyen_quan_ly,
        'page_obj': Paginator(ngu_canh['rows'], 6 if la_ca_nhan else 12).get_page(request.GET.get('page')),
        'page_query': tham_so_phan_trang(request), 'director': has_role(request.user, DIRECTOR),
        'initials': ''.join(tu[0] for tu in nhan_vien.full_name.split()[-2:]).upper(),
        'tabs': [('', 'Tất cả'), ('late', 'Đi trễ'), ('leave', 'Nghỉ phép'), ('absent', 'Nghỉ không phép')],
    })
    return render(request, 'attendance/month.html', ngu_canh)


@login_required
@require_POST
def duyet_bang_cong_nhan_vien(request, employee_id, period_id):
    require_role(request.user, HR, DIRECTOR)
    nhan_vien = get_object_or_404(visible_employees(request.user), pk=employee_id)
    ky_cong = get_object_or_404(KyCong, pk=period_id)
    try:
        ban_chot = duyet_cong_nhan_vien(request.user, nhan_vien, ky_cong.pk)
    except ValidationError as loi:
        messages.error(request, '; '.join(loi.messages))
    else:
        messages.success(request, f'Đã duyệt bảng công của {nhan_vien.full_name} tháng {ky_cong}.')
        if getattr(ban_chot, 'payroll_error', ''):
            messages.warning(request, 'Chưa đủ điều kiện cập nhật lương: ' + ban_chot.payroll_error)
    return redirect(reverse('bang_cong:cong-nhan-vien', args=[nhan_vien.pk]) + '?' +
                    urlencode({'month': ky_cong.thang, 'year': ky_cong.nam}))


@login_required
def lich_su_dieu_chinh(request, employee_id):
    pham_vi = Employee.objects.filter(Q(pk__in=visible_employees(request.user).values('pk')) | Q(user=request.user))
    nhan_vien = get_object_or_404(pham_vi, pk=employee_id)
    ngu_canh = du_lieu_lich_su_cong(request, nhan_vien)
    ngu_canh.update({
        'employee': nhan_vien, 'can_export': has_role(request.user, HR, DIRECTOR),
        'page_obj': Paginator(ngu_canh['rows'], 20).get_page(request.GET.get('page')),
        'page_query': tham_so_phan_trang(request),
    })
    return render(request, 'attendance/history.html', ngu_canh)


@login_required
def xuat_bang_cong(request, employee_id):
    require_role(request.user, HR, DIRECTOR)
    nhan_vien = get_object_or_404(visible_employees(request.user), pk=employee_id)
    che_do = request.GET.get('mode', 'month')
    if che_do not in ('month', 'history'):
        raise Http404
    ngu_canh = du_lieu_lich_su_cong(request, nhan_vien) if che_do == 'history' else du_lieu_cong_thang(request, nhan_vien)
    if not ngu_canh['form'].is_valid() or (che_do == 'history' and not ngu_canh['period_form'].is_valid()):
        return HttpResponse('Bộ lọc không hợp lệ.', status=400)
    tep_csv = io.StringIO(newline='')
    if che_do == 'history':
        tieu_de = [
            'Thời gian điều chỉnh', 'Ngày công', 'Trường', 'Giá trị cũ',
            'Giá trị mới', 'Người sửa', 'Lý do',
        ]
        gia_tri = (
            [dong['time'].isoformat(), dong['date'], dong['field'], dong['old'],
             dong['new'], dong['actor'], dong['reason']]
            for dong in ngu_canh['rows']
        )
    else:
        tieu_de = [
            'Mã NV', 'Họ tên', 'Ngày', 'Giờ vào', 'Giờ ra', 'Tình trạng',
            'Phút muộn', 'Giờ làm', 'Công hưởng lương', 'Ghi chú', 'OT tự động (giờ)',
        ]
        gia_tri = []
        for dong in ngu_canh['rows']:
            ban_ghi = dong['record']
            gia_tri.append([
                nhan_vien.code, nhan_vien.full_name, dong['date'],
                getattr(ban_ghi, 'gio_vao', ''), getattr(ban_ghi, 'gio_ra', ''), dong['label'],
                getattr(ban_ghi, 'so_phut_tre', ''), getattr(ban_ghi, 'so_gio_lam', ''),
                getattr(ban_ghi, 'tong_cong', ''), getattr(ban_ghi, 'ghi_chu', ''), dong['ot'],
            ])
    bo_ghi = csv.writer(tep_csv)
    bo_ghi.writerow(tieu_de)
    for dong in gia_tri:
        cac_o = (str(gia_tri_o) if gia_tri_o is not None else '' for gia_tri_o in dong)
        # Chặn nội dung có thể bị phần mềm bảng tính hiểu thành công thức.
        bo_ghi.writerow(
            "'" + gia_tri_o if gia_tri_o.lstrip().startswith(('=', '+', '-', '@')) else gia_tri_o
            for gia_tri_o in cac_o
        )
    phan_hoi = HttpResponse('\ufeff' + tep_csv.getvalue(), content_type='text/csv; charset=utf-8')
    phan_hoi['Content-Disposition'] = f'attachment; filename="attendance-{nhan_vien.pk}-{che_do}.csv"'
    return phan_hoi


@login_required
def chi_tiet_cham_cong(request, pk):
    dong = get_object_or_404(ChamCong.objects.select_related('nhan_vien'), pk=pk,
                            nhan_vien__in=visible_employees(request.user))
    ngu_canh = {
        'row': dong,
        'can_edit': has_role(request.user, HR, DIRECTOR) and not cham_cong_da_khoa(dong),
        **du_lieu_tang_ca(dong),
    }
    return render(request, 'attendance/detail.html', ngu_canh)


@login_required
def sua_cham_cong(request, pk=None):
    require_role(request.user, HR, DIRECTOR)
    dong = get_object_or_404(ChamCong, pk=pk, nhan_vien__in=visible_employees(request.user)) if pk else None
    if dong and cham_cong_da_khoa(dong):
        raise PermissionDenied('Kỳ công đã duyệt, không được chỉnh sửa chấm công.')
    ban_dau = {'employee': request.GET.get('employee'), 'date': request.GET.get('date')} if not dong else None
    form = ChamCongForm(request.user, request.POST or None, instance=dong, initial=ban_dau)
    if request.method == 'POST' and form.is_valid():
        try:
            da_luu = luu_cham_cong(request.user, form.save(commit=False), form.cleaned_data['reason'])
        except KyCong.DoesNotExist:
            form.add_error(None, 'Chưa tạo kỳ công cho tháng này trong trang quản trị.')
        except ValidationError as loi:
            form.add_error(None, '; '.join(loi.messages))
        except IntegrityError:
            form.add_error(None, 'Đã có bản ghi nhân viên/ngày này hoặc dữ liệu không hợp lệ.')
        else:
            messages.success(request, 'Đã lưu và tính lại công.')
            return redirect('bang_cong:chi-tiet', pk=da_luu.pk)
    return render(request, 'attendance/edit.html', {'form': form, 'title': 'Ghi nhận / chỉnh sửa chấm công', 'row': dong})


@login_required
@require_POST
def doi_trang_thai_ky_cong(request, pk):
    require_role(request.user, DIRECTOR)
    ky_cong = get_object_or_404(KyCong, pk=pk)
    try:
        xu_ly_trang_thai_ky_cong(request.user, pk, request.POST.get('action'), request.POST.get('reason', ''))
    except ValidationError as loi:
        messages.error(request, '; '.join(loi.messages))
    else:
        messages.success(request, 'Đã cập nhật trạng thái kỳ công.')
    return redirect(reverse('bang_cong:danh-sach') + '?' + urlencode({'month': ky_cong.thang, 'year': ky_cong.nam}))
