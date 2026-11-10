import mimetypes

from django.contrib.auth.decorators import login_required
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe
from employees.access import has_role, require_role, HR, DIRECTOR, MANAGER
from employees.access import visible_employees
from employees.models import Employee, Education, LaborContract
from leaves.models import LeaveRequest
from django.core.paginator import Paginator
from .dashboard import DashboardFilter, dashboard_context


@login_required
def dashboard(request):
    if not has_role(request.user, HR, DIRECTOR, MANAGER):
        return redirect('attendance:list')
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
        (LaborContract, 'contract_file'), (LeaveRequest, 'evidence'),
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
