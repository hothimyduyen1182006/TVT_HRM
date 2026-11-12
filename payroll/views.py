"""Xử lý request Bảng lương; tách truy vấn hiển thị khỏi thao tác ghi dữ liệu."""
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from employees.access import visible_employees, has_role, require_role, HR, DIRECTOR, MANAGER
from .models import PayrollRecord, PayrollPeriod, PayrollInput, PayrollAdjustment
from .forms import PayrollInputForm, AdjustmentForm, PayrollFilter, PayslipFilter
from .services.calculations import calculate_payroll
from .services.workflow import change_payroll, approve_record, record_approval_error
from .services.exports import export_records
from .services.presentation import payslip_context, scoped_records, employee_records
from .services.inputs import save_input


@login_required
def record_list(request):
    if not has_role(request.user, HR, DIRECTOR, MANAGER):
        messages.error(request, 'Bạn không có quyền truy cập chức năng quản lý lương.')
        target = reverse('payroll:personal')
        period_query = urlencode({key: request.GET[key] for key in ['month', 'year'] if request.GET.get(key)})
        return redirect(target + ('?' + period_query if period_query else ''))
    form = PayrollFilter(request.user, request.GET)
    rows = scoped_records(request.user, form)
    if has_role(request.user, HR, DIRECTOR):
        for row in rows:
            row.approval_error = record_approval_error(row) if row.status == 'pending' else ''
    period = None
    if form.is_valid():
        period = PayrollPeriod.objects.filter(attendance_period__month=form.cleaned_data['month'],
                                               attendance_period__year=form.cleaned_data['year']).first()
    context = {'form': form, 'rows': rows, 'period': period,
                  'has_approved_records': period.records.filter(status='approved').exists() if period else False,
                  'month_label': str(form['month'].value()).zfill(2), 'year_label': form['year'].value(),
                  'can_manage': has_role(request.user, HR, DIRECTOR), 'director': has_role(request.user, DIRECTOR)}
    return render(request, 'payroll/list.html', context)


@login_required
def personal(request):
    form = PayslipFilter(request.GET)
    row = None
    if form.is_valid():
        row = employee_records(request.user).filter(period__attendance_period__month=form.cleaned_data['month'],
            period__attendance_period__year=form.cleaned_data['year']).first()
    context = payslip_context(row) if row else {}
    context.update({'form': form, 'row': row, 'personal': True,
                    'month_label': str(form['month'].value()).zfill(2), 'year_label': form['year'].value(),
                    'requires_approval': False})
    return render(request, 'payroll/personal.html', context)


@login_required
def detail(request, pk):
    can_view_team = has_role(request.user, HR, DIRECTOR, MANAGER)
    queryset = PayrollRecord.objects.select_related('period__attendance_period').filter(
        employee__in=visible_employees(request.user)) if can_view_team else employee_records(request.user)
    row = get_object_or_404(queryset, pk=pk)
    period = row.period.attendance_period
    form = PayslipFilter({'month': period.month, 'year': period.year})
    context = payslip_context(row)
    context.update({'form': form, 'personal': not can_view_team, 'month_label': f'{period.month:02}',
                    'year_label': period.year, 'requires_approval': False})
    return render(request, 'payroll/detail.html', context)


@login_required
@require_POST
def approve_employee_payroll(request, pk):
    require_role(request.user, DIRECTOR)
    row = get_object_or_404(PayrollRecord.objects.select_related('period__attendance_period'), pk=pk,
                            employee__in=visible_employees(request.user))
    try:
        approve_record(request.user, row.pk)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        messages.success(request, f'Đã duyệt bảng lương của {row.employee_name}.')
    attendance = row.period.attendance_period
    return redirect(reverse('payroll:list') + '?' + urlencode({'month': attendance.month, 'year': attendance.year}))


@login_required
@require_POST
def transition(request, pk):
    require_role(request.user, HR, DIRECTOR)
    period = get_object_or_404(PayrollPeriod.objects.select_related('attendance_period'), pk=pk)
    try:
        action = request.POST.get('action')
        if action == 'calculate':
            calculate_payroll(request.user, pk, request.POST.get('reason', ''))
        else:
            change_payroll(request.user, pk, action, request.POST.get('reason', ''), request.POST.get('evidence', ''))
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        messages.success(request, 'Đã cập nhật bảng lương.')
    return redirect(reverse('payroll:list') + '?' + urlencode({
        'month': period.attendance_period.month, 'year': period.attendance_period.year}))


@login_required
@require_POST
def export(request, fmt):
    require_role(request.user, HR, DIRECTOR)
    form = PayrollFilter(request.user, request.POST)
    if not form.is_valid():
        return render(request, 'form.html', {'form': form, 'title': 'Bộ lọc xuất không hợp lệ'}, status=400)
    try:
        data = form.cleaned_data
        return export_records(request.user, scoped_records(request.user, form), fmt, data['month'], data['year'],
                              {'employee': data['employee'].pk if data['employee'] else None,
                               'department': data['department'].pk if data['department'] else None,
                               'q': data['q'], 'status': data['status']})
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
        values = {key: request.POST[key] for key in ['month', 'year', 'q', 'status', 'department', 'employee']
                  if request.POST.get(key)}
        return redirect(reverse('payroll:list') + '?' + urlencode(values))


@login_required
def inputs(request):
    require_role(request.user, HR, DIRECTOR)
    if request.GET.get('employee'):
        try:
            employee = get_object_or_404(visible_employees(request.user), pk=int(request.GET['employee']))
        except (ValueError, TypeError):
            raise Http404
        query = urlencode({key: request.GET[key] for key in ['month', 'year'] if request.GET.get(key)})
        return redirect(reverse('employee_detail', args=[employee.pk]) + ('?' + query if query else '') + '#payroll-settings')
    return redirect('employees')


@login_required
def edit_input(request, kind, pk=None, employee_id=None):
    require_role(request.user, HR, DIRECTOR)
    if kind not in ['tax', 'adjustment']:
        raise Http404
    model, form_class = (PayrollInput, PayrollInputForm) if kind == 'tax' else (PayrollAdjustment, AdjustmentForm)
    obj = get_object_or_404(model, pk=pk, employee__in=visible_employees(request.user)) if pk is not None else None
    employee = get_object_or_404(visible_employees(request.user), pk=employee_id) if employee_id is not None else None
    if obj and employee and obj.employee_id != employee.pk:
        raise Http404
    settings_employee=employee or (obj.employee if obj else None)
    if settings_employee and settings_employee.payroll_settings is not None:
        return redirect(reverse('employee_edit',args=[settings_employee.pk])+'#salary-settings')
    initial = {}
    if not obj and (request.GET.get('period') or request.GET.get('employee')):
        try:
            if request.GET.get('period'):
                initial['period'] = get_object_or_404(PayrollPeriod, pk=int(request.GET['period']), status='pending')
            if request.GET.get('employee'):
                initial['employee'] = get_object_or_404(visible_employees(request.user), pk=int(request.GET['employee']))
        except (ValueError, TypeError):
            raise Http404
    if employee:
        initial['employee'] = employee
    form = form_class(request.user, request.POST or None, instance=obj, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            value, changed = save_input(request.user, form.save(commit=False))
        except (ValidationError, IntegrityError) as exc:
            form.add_error(None, '; '.join(exc.messages) if isinstance(exc, ValidationError) else 'Dữ liệu bị trùng.')
        else:
            messages.success(request, 'Đã lưu dữ liệu và tự cập nhật phiếu lương đủ điều kiện.' if changed else 'Dữ liệu không thay đổi.')
            if getattr(value, 'payroll_error', ''):
                messages.warning(request, 'Chưa đủ điều kiện cập nhật lương: ' + value.payroll_error)
            at = value.period.attendance_period
            return redirect(reverse('employee_detail', args=[value.employee_id]) + '?' + urlencode({'month': at.month, 'year': at.year}) + '#payroll-settings')
    selected_period = obj.period if obj else initial.get('period')
    back_query = urlencode({'month': selected_period.attendance_period.month, 'year': selected_period.attendance_period.year}) if selected_period else ''
    selected_employee = obj.employee if obj else initial.get('employee')
    back_url = reverse('employee_detail', args=[selected_employee.pk]) + ('?' + back_query if back_query else '') + '#payroll-settings' if selected_employee else reverse('employees')
    return render(request, 'payroll/input_form.html', {'form': form, 'kind': kind, 'locked': obj.is_locked if obj else False,
        'input_object': obj, 'back_query': back_query, 'back_url': back_url,
        'title': 'Thiết lập tính lương' if kind == 'tax' else 'Phụ cấp / khấu trừ theo kỳ'})
