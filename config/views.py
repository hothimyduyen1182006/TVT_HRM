from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from employees.access import has_role, require_role, HR, DIRECTOR, MANAGER
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
