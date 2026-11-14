import mimetypes

from django.contrib.auth.decorators import login_required
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from nhan_vien.access import has_role, require_role, HR, DIRECTOR, MANAGER
from nhan_vien.access import visible_employees
from nhan_vien.models import Employee, Education, LaborContract
from nghi_phep.models import LeaveRequest
from django.core.paginator import Paginator
from .dashboard import DashboardFilter, dashboard_context
from django.urls import reverse
from django.utils import timezone
from urllib.parse import urlencode
from bang_luong.models import Luong
from bang_luong.services.hien_thi import phieu_luong_ca_nhan


@login_required
@require_safe
def home(request):
    employee=Employee.objects.filter(user=request.user).first()
    can_manage=has_role(request.user,HR,DIRECTOR,MANAGER)
    name=(employee.full_name if employee else '') or request.user.get_full_name() or request.user.get_username()
    latest=phieu_luong_ca_nhan(request.user).order_by(
        '-ky_luong__attendance_period__nam','-ky_luong__attendance_period__thang','-ngay_tinh','-pk').first()
    today=timezone.localdate()
    period=latest.ky_luong.attendance_period if latest else None
    payroll_url=reverse('bang_luong:personal')+'?'+urlencode({'month':period.thang if period else today.month,
        'year':period.nam if period else today.year})
    return render(request,'home.html',{
        'display_name':name,
        'attendance_url':reverse('bang_cong:ca-nhan') if employee else (reverse('bang_cong:danh-sach') if can_manage else ''),
        'attendance_description':'Theo dõi công của bạn' if employee else ('Xem dữ liệu theo quyền' if can_manage else 'Chưa liên kết hồ sơ nhân viên'),
        'payroll_url':payroll_url if employee or not can_manage else reverse('bang_luong:list'),
        'payroll_description':f'Phiếu lương mới nhất · {period.thang:02}/{period.nam}' if period else (
            'Xem phiếu lương của bạn' if employee or not can_manage else 'Xem bảng lương theo quyền'),
        'leave_url':reverse('nghi_phep:list') if can_manage or (employee and employee.is_active) else '',
        'leave_title':'Quản lý nghỉ phép' if can_manage else 'Đăng ký nghỉ phép',
        'leave_description':'Xem các yêu cầu theo quyền' if can_manage else (
            'Tạo đơn nghỉ phép' if employee and employee.is_active else 'Cần hồ sơ nhân viên đang hoạt động'),
    })


@login_required
def dashboard(request):
    if not has_role(request.user, HR, DIRECTOR, MANAGER):
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
    require_role(request.user, HR, DIRECTOR, MANAGER)
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
    employees = visible_employees(request.user)
    for model, field_name in [
        (Employee, 'avatar'), (Education, 'certificate_file'),
        (LaborContract, 'contract_file'), (LeaveRequest, 'Tep_dinh_kem'),
    ]:
        scope = {'pk__in': employees.values('pk')} if model is Employee else {'employee__in': employees}
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
