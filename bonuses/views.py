from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from employees.access import require_role, DIRECTOR, HR
from employees.filters import PeriodFilter
from .models import Bonus


@login_required
def bonus_list(request):
    require_role(request.user, DIRECTOR, HR)
    form = PeriodFilter(request.user, request.GET)
    rows = Bonus.objects.none()
    if form.is_valid():
        rows = Bonus.objects.select_related('employee__department').filter(
            employee__in=form.employee_scope(request.user), month=form.cleaned_data['month'],
            year=form.cleaned_data['year']).order_by('employee__code', 'name')
    return render(request, 'bonuses/list.html', {'form': form, 'rows': rows})
