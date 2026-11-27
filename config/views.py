import mimetypes

from django.contrib.auth.decorators import login_required
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from nhan_vien.access import co_vai_tro, yeu_cau_vai_tro, NHAN_SU, GIAM_DOC, TRUONG_PHONG
from nhan_vien.access import nhan_vien_duoc_hien_thi
from nhan_vien.models import NhanVien, HocVan, HopDongLaoDong
from nghi_phep.models import DonNghiPhep
from django.core.paginator import Paginator
from .dashboard import DashboardFilter, dashboard_context
from django.urls import reverse
from django.utils import timezone
from urllib.parse import urlencode
from bang_luong.models import Luong
from bang_luong.services.xuat_luong_service import phieu_luong_ca_nhan


@login_required
@require_safe
def home(request):
    employee=NhanVien.objects.filter(nguoi_dung=request.user).first()
    can_manage=co_vai_tro(request.user,NHAN_SU,GIAM_DOC,TRUONG_PHONG)
    name=(employee.ho_va_ten if employee else '') or request.user.get_full_name() or request.user.get_username()
    latest=phieu_luong_ca_nhan(request.user).order_by(
        '-tong_hop__nam','-tong_hop__thang','-pk').first()
    today=timezone.localdate()
    thang = latest.tong_hop.thang if latest else today.month
    nam = latest.tong_hop.nam if latest else today.year
    payroll_url=reverse('bang_luong:ca_nhan')+'?'+urlencode({'thang':thang, 'nam':nam})
    bonus_url = reverse('thuong:list' if can_manage else 'thuong:personal')
    return render(request,'home.html',{
        'display_name':name,
        'can_manage': can_manage,
        'attendance_url': reverse('bang_cong:danh-sach') if can_manage else (
            reverse('bang_cong:ca-nhan') if employee else ''
        ),
        'attendance_description': 'Theo dõi tình hình chấm công' if can_manage else 'Theo dõi ngày công của bạn',
        'payroll_url': reverse('bang_luong:danh_sach') if can_manage else payroll_url,
        'bonus_url':bonus_url,
        'bonus_description': 'Theo dõi và xử lý thưởng' if can_manage else 'Xem các khoản thưởng của bạn',
        'payroll_description': 'Theo dõi thông tin tiền lương' if can_manage else (
            f'Phiếu lương mới nhất · {thang:02}/{nam}' if latest else 'Xem phiếu lương của bạn'
        ),
        'leave_url':reverse('nghi_phep:list') if can_manage or (employee and employee.dang_hoat_dong) else '',
        'leave_title': 'Quản lý nghỉ phép' if can_manage else 'Nghỉ phép cá nhân',
        'leave_description': 'Theo dõi và xử lý đơn nghỉ phép' if can_manage else 'Gửi và theo dõi đơn nghỉ phép',
    })


@login_required
def dashboard(request):
    if not co_vai_tro(request.user, NHAN_SU, GIAM_DOC, TRUONG_PHONG):
        return redirect('bang_cong:danh-sach')
    form = DashboardFilter(request.user, request.GET)
    context = dashboard_context(request.user, form) if form.is_valid() else {}
    query = request.GET.copy()
    query.pop('page', None)
    context.update({'form': form, 'page_obj': Paginator(context.get('employee_rows', []), 10).get_page(request.GET.get('page')),
                    'page_query': query.urlencode()})
    return render(request, 'dashboard.html', context)


@login_required
def departments(request):
    yeu_cau_vai_tro(request.user, NHAN_SU, GIAM_DOC, TRUONG_PHONG)
    form = DashboardFilter(request.user, request.GET)
    context = dashboard_context(request.user, form) if form.is_valid() else {}
    context['form'] = form
    return render(request, 'departments.html', context)


@never_cache
@login_required
@require_safe
def protected_media(request, path):
    """Serve only registered employee files within the caller's existing scope."""
    if any(part in ('', '.', '..') for part in path.split('/')) or any(
            char in path for char in ('\\', '\x00', ':')):
        raise Http404
    employees = nhan_vien_duoc_hien_thi(request.user)
    for model, field_name in [
        (NhanVien, 'hinh_anh'), (HocVan, 'tep_bang_cap'),
        (HopDongLaoDong, 'tep_hop_dong'), (DonNghiPhep, 'tep_dinh_kem'),
    ]:
        if model is NhanVien:
            scope = {'pk__in': employees.values('pk')}
        elif model in (HocVan, HopDongLaoDong):
            scope = {'ho_so_ca_nhan__in': employees}
        elif model is DonNghiPhep:
            scope = {'nhan_vien__in': employees}
        else:
            scope = {'employee__in': employees}
        record = model.objects.filter(**scope, **{field_name: path}).first()
        if record is None:
            continue
        attachment = getattr(record, field_name)
        content_type = mimetypes.guess_type(attachment.name)[0] or 'application/octet-stream'
        inline_image = content_type in ('image/jpeg', 'image/png', 'image/webp', 'image/gif')
        try:
            opened = attachment.open('rb')
        except (OSError, SuspiciousFileOperation):
            raise Http404
        response = FileResponse(opened, content_type=content_type,
                                as_attachment=not inline_image, filename=path.rsplit('/', 1)[-1])
        response['X-Content-Type-Options'] = 'nosniff'
        return response
    raise Http404
