from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from .access import DIRECTOR, HR, MANAGER, has_role, visible_employees
from .forms import (
    DashboardEmployeeFilter,
    EducationForm,
    EmployeeForm,
    LaborContractForm,
    PersonalProfileForm,
    SalarySettingsForm,
)
from .models import Education, Employee, LaborContract


def payroll_settings_context(request, employee):
    if not employee or not (
        employee.user_id == request.user.pk or has_role(request.user, HR, DIRECTOR)
    ):
        return {}
    return {
        'shared_salary_settings': employee.payroll_settings,
        'can_manage_salary': has_role(request.user, HR, DIRECTOR),
        'salary_form': SalarySettingsForm(employee),
    }


@login_required
def payroll_settings_edit(request, employee_id, kind, record_id=None):
    if not has_role(request.user,HR,DIRECTOR):
        return _forbidden(request)
    get_object_or_404(visible_employees(request.user),pk=employee_id)
    from bang_luong.models import PayrollAdjustment, PayrollInput

    if kind not in ('tax', 'adjustment'):
        raise Http404
    if record_id is not None:
        model = PayrollInput if kind == 'tax' else PayrollAdjustment
        get_object_or_404(model, pk=record_id, employee_id=employee_id)
    return redirect('employee_edit', employee_id=employee_id)


MANAGEMENT_ROLES = (HR, DIRECTOR)
DIRECTORY_ROLES = (HR, DIRECTOR, MANAGER)


def _forbidden(request):
    return render(request, 'employees/forbidden.html', status=403)


@login_required
def employee_list(request):
    if not has_role(request.user, *DIRECTORY_ROLES):
        return _forbidden(request)
    rows = visible_employees(request.user)
    dashboard_filter = DashboardEmployeeFilter(request.GET)
    if dashboard_filter.is_valid():
        selected_day = dashboard_filter.cleaned_data['active_as_of']
        if selected_day:
            rows = rows.filter(is_active=True, hire_date__lte=selected_day)
        gender = dashboard_filter.cleaned_data['gender']
        if gender == 'unknown':
            rows = rows.exclude(gender__in=['Nam', 'Nữ'])
        elif gender:
            rows = rows.filter(gender=gender)
    else:
        rows = rows.none()
    filters = {
        'q': request.GET.get('q', '').strip()[:100],
        'department': request.GET.get('department', '').strip(),
        'position': request.GET.get('position', '').strip(),
        'status': request.GET.get('status', '').strip(),
        'hire_from': request.GET.get('hire_from', '').strip(),
        'hire_to': request.GET.get('hire_to', '').strip(),
    }
    if filters['q']:
        rows = rows.filter(
            Q(code__icontains=filters['q'])
            | Q(full_name__icontains=filters['q'])
            | Q(user__username__icontains=filters['q'])
        )
    if filters['department'].isdigit():
        rows = rows.filter(department_id=filters['department'])
    if filters['position'].isdigit():
        rows = rows.filter(position_id=filters['position'])
    if filters['status'] in dict(Employee.EMPLOYMENT_STATUS_CHOICES):
        rows = rows.filter(employment_status=filters['status'])
    hire_from = parse_date(filters['hire_from']) if filters['hire_from'] else None
    hire_to = parse_date(filters['hire_to']) if filters['hire_to'] else None
    if hire_from:
        rows = rows.filter(hire_date__gte=hire_from)
    if hire_to:
        rows = rows.filter(hire_date__lte=hire_to)

    departments = rows.model.department.field.remote_field.model.objects.all()
    if has_role(request.user, MANAGER) and not has_role(request.user, HR, DIRECTOR):
        departments = departments.filter(manager__user=request.user)
    positions = rows.model.position.field.remote_field.model.objects.select_related('department')
    positions = positions.filter(department__in=departments)
    return render(request, 'employees/list.html', {
        'dashboard_filter': dashboard_filter,
        'rows': rows.select_related('department', 'position', 'user'),
        'filters': filters,
        'departments': departments.distinct(),
        'positions': positions,
        'status_choices': Employee.EMPLOYMENT_STATUS_CHOICES,
        'can_manage': has_role(request.user, *MANAGEMENT_ROLES),
    })


@login_required
def employee_detail(request, employee_id):
    if not has_role(request.user, *DIRECTORY_ROLES):
        return _forbidden(request)
    employee = get_object_or_404(Employee.objects.select_related('user', 'department', 'position'), pk=employee_id)
    if not visible_employees(request.user).filter(pk=employee.pk).exists():
        return _forbidden(request)
    return render(request, 'employees/detail.html', {
        'employee': employee,
        'can_manage': False,
        **payroll_settings_context(request, employee),
    })


@login_required
def personal_profile(request):
    employee = Employee.objects.filter(user=request.user).select_related(
        'user', 'department', 'position').first()
    return render(request, 'employees/detail.html', {
        'employee': employee,
        'personal_view': True,
        'can_manage': True,
        **payroll_settings_context(request, employee),
    })


@login_required
def personal_profile_edit(request):
    employee = get_object_or_404(Employee.objects.select_related('user'), user=request.user)
    form = PersonalProfileForm(request.POST or None, request.FILES or None, instance=employee)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Hồ sơ cá nhân đã được cập nhật.')
        return redirect('personal_profile')
    return render(request, 'employees/personal_profile_form.html', {'form': form, 'employee': employee})


@login_required
def employee_create(request):
    if not has_role(request.user, *MANAGEMENT_ROLES):
        return _forbidden(request)
    form = EmployeeForm(request.POST or None, request.FILES or None)
    salary_form=SalarySettingsForm(data=request.POST if request.method=='POST' and any(key.startswith('salary-') for key in request.POST) else None)
    if request.method == 'POST' and form.is_valid() and (not salary_form.is_bound or salary_form.is_valid()):
        employee = form.save()
        if salary_form.is_bound:
            from bang_luong.services.inputs import save_employee_settings
            save_employee_settings(request.user,employee,salary_form.settings_data())
        messages.success(request, 'Thêm mới nhân viên thành công.')
        return redirect('employee_detail', employee_id=employee.pk)
    return render(request, 'employees/employee_form.html', {
        'form': form,
        'salary_form': salary_form,
        'is_create': True,
    })


@login_required
def employee_edit(request, employee_id):
    if not has_role(request.user, *MANAGEMENT_ROLES):
        return _forbidden(request)
    employee = get_object_or_404(Employee.objects.select_related('user'), pk=employee_id)
    basic_data=request.POST or None if request.POST.get('action')!='save_salary' else None
    form = EmployeeForm(basic_data, request.FILES or None, instance=employee)
    salary_form=SalarySettingsForm(employee,request.POST if request.method=='POST' and any(key.startswith('salary-') for key in request.POST) else None)
    if request.method=='POST' and request.POST.get('action')=='save_salary':
        if salary_form.is_bound and salary_form.is_valid():
            from bang_luong.services.inputs import save_employee_settings
            employee=save_employee_settings(request.user,employee,salary_form.settings_data())
            messages.success(request,'Đã lưu thiết lập tính lương dùng chung của nhân viên.')
            for error in employee.payroll_errors: messages.warning(request,error)
            return redirect('employee_detail',employee_id=employee.pk)
    elif request.method == 'POST' and form.is_valid() and (not salary_form.is_bound or salary_form.is_valid()):
        form.save()
        if salary_form.is_bound:
            from bang_luong.services.inputs import save_employee_settings
            employee=save_employee_settings(request.user,employee,salary_form.settings_data())
        if set(form.changed_data) & {'base_salary', 'code', 'full_name', 'department'}:
            from bang_luong.models import PayrollPeriod
            from bang_luong.services.calculations import refresh_employee_payroll
            periods = PayrollPeriod.objects.filter(status='pending').select_related('attendance_period').order_by('attendance_period_id')
            for period in periods:
                attendance = period.attendance_period
                error = refresh_employee_payroll(request.user, employee.pk, attendance.nam, attendance.thang)
                if error:
                    messages.warning(request, error)
        messages.success(request, 'Sửa hồ sơ thành công.')
        return redirect('employee_detail', employee_id=employee.pk)
    return render(request, 'employees/employee_form.html', {
        'form': form,
        'salary_form': salary_form,
        'employee': employee,
        'can_manage': True,
    })


def _can_edit_employee_records(user, employee):
    return has_role(user, *MANAGEMENT_ROLES) or employee.user_id == user.pk


def _employee_profile_redirect(request, employee):
    if employee.user_id == request.user.pk:
        return redirect('personal_profile')
    return redirect('employee_detail', employee_id=employee.pk)


def _record_form(request, employee_id, record_id, model, form_class, kind, title):
    employee = get_object_or_404(Employee, pk=employee_id)
    if not _can_edit_employee_records(request.user, employee):
        return _forbidden(request)
    record = get_object_or_404(model, pk=record_id, employee=employee) if record_id else None
    form = form_class(request.POST or None, request.FILES or None, instance=record)
    if request.method == 'POST' and form.is_valid():
        item = form.save(commit=False)
        item.employee = employee
        item.save()
        messages.success(request, f'{title} đã được lưu.')
        return _employee_profile_redirect(request, employee)
    return render(request, 'employees/record_form.html', {
        'form': form,
        'employee': employee,
        'record': record,
        'kind': kind,
        'title': title,
        'is_edit': record is not None,
        'personal_view': employee.user_id == request.user.pk,
    })


@login_required
def education_edit(request, employee_id, record_id=None):
    return _record_form(request, employee_id, record_id, Education, EducationForm, 'education', 'Thông tin học vấn')


@login_required
def contract_edit(request, employee_id, record_id=None):
    return _record_form(request, employee_id, record_id, LaborContract, LaborContractForm, 'contract', 'Thông tin hợp đồng lao động')


@login_required
@require_POST
def education_delete(request, employee_id, record_id):
    employee = get_object_or_404(Employee, pk=employee_id)
    if not _can_edit_employee_records(request.user, employee):
        return _forbidden(request)
    record = get_object_or_404(Education, pk=record_id, employee=employee)
    if record.certificate_file:
        record.certificate_file.delete(save=False)
    record.delete()
    messages.success(request, 'Đã xóa thông tin học vấn.')
    return _employee_profile_redirect(request, employee)


@login_required
@require_POST
def contract_delete(request, employee_id, record_id):
    employee = get_object_or_404(Employee, pk=employee_id)
    if not _can_edit_employee_records(request.user, employee):
        return _forbidden(request)
    record = get_object_or_404(LaborContract, pk=record_id, employee=employee)
    if record.contract_file:
        record.contract_file.delete(save=False)
    record.delete()
    messages.success(request, 'Đã xóa hợp đồng lao động.')
    return _employee_profile_redirect(request, employee)
