from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from employees.access import require_role, DIRECTOR, HR
from employees.filters import PeriodFilter
from .models import LeaveDay


@login_required
def leave_list(request):
    require_role(request.user, DIRECTOR, HR)
    form = PeriodFilter(request.user, request.GET)
    rows = LeaveDay.objects.none()
    if form.is_valid():
        rows = LeaveDay.objects.select_related('employee__department').filter(
            employee__in=form.employee_scope(request.user), date__month=form.cleaned_data['month'],
            date__year=form.cleaned_data['year']).order_by('-date', 'employee__code')
    return render(request, 'leaves/list.html', {'form': form, 'rows': rows})
