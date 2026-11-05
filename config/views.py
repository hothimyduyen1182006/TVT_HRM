from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from employees.access import has_role, HR, DIRECTOR, MANAGER


@login_required
def dashboard(request):
    if not has_role(request.user, HR, DIRECTOR, MANAGER):
        return redirect('attendance:list')
    return render(request, 'dashboard.html')
