from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.http import Http404
from employees.access import visible_employees, has_role, require_role, HR, DIRECTOR, MANAGER
from .models import PayrollRecord, PayrollPeriod, PayrollInput, PayrollAdjustment
from .forms import PayrollInputForm, AdjustmentForm, PayrollFilter, PayslipFilter, PayrollInputFilter
from django.db import IntegrityError
from .services.calculations import calculate_payroll
from .services.workflow import change_payroll, approve_record, record_approval_error
from .services.exports import export_records
from .services.presentation import payslip_context
from django.db.models import Q
from django.urls import reverse
from urllib.parse import urlencode
from decimal import Decimal
from datetime import date
import calendar
from .services.inputs import save_input


def scoped_records(user, form):
    if not form.is_valid():
        return PayrollRecord.objects.none()
    data = form.cleaned_data
    rows = PayrollRecord.objects.select_related('period__attendance_period').filter(
        employee__in=form.employee_scope(user), period__attendance_period__month=data['month'],
        period__attendance_period__year=data['year'])
    if data.get('q'):
        rows = rows.filter(Q(employee_name__icontains=data['q']) | Q(employee_code__icontains=data['q']))
    if data.get('status'):
        rows = rows.filter(status=data['status'])
    return rows


@login_required
def record_list(request):
    if not has_role(request.user, HR, DIRECTOR, MANAGER):
        return personal(request)
    form = PayrollFilter(request.user, request.GET)
    rows = scoped_records(request.user, form)
    if has_role(request.user, DIRECTOR):
        for row in rows:
            row.approval_error = record_approval_error(row) if row.status == 'pending' else ''
    period = None
    if form.is_valid():
        period = PayrollPeriod.objects.filter(attendance_period__month=form.cleaned_data['month'],
                                               attendance_period__year=form.cleaned_data['year']).first()
    return render(request, 'payroll/list.html', {'form': form, 'rows': rows, 'period': period,
                  'has_approved_records': period.records.filter(status='approved').exists() if period else False,
                  'month_label': str(form['month'].value()).zfill(2), 'year_label': form['year'].value(),
                  'can_manage': has_role(request.user, HR, DIRECTOR), 'director': has_role(request.user, DIRECTOR)})


def employee_records(user):
    # Giữ điều kiện hiển thị hiện có cho đến khi nhóm xác nhận mâu thuẫn UC-7.1/ảnh mẫu.
    return PayrollRecord.objects.select_related('period__attendance_period').filter(employee__user=user)


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
    form = PayrollInputFilter(request.user, request.GET)
    period, employee_rows = None, []
    input_rows, adjustments = PayrollInput.objects.none(), PayrollAdjustment.objects.none()
    counts = {'total': 0, 'missing': 0, 'draft': 0, 'verified': 0, 'locked': 0}
    if form.is_valid():
        data = form.cleaned_data
        scope = form.employee_scope(request.user)
        scope = scope.filter(hire_date__lte=date(data['year'], data['month'], calendar.monthrange(data['year'], data['month'])[1]))
        if data['q']:
            scope = scope.filter(Q(code__icontains=data['q']) | Q(full_name__icontains=data['q']))
        period = PayrollPeriod.objects.select_related('attendance_period').filter(
            attendance_period__month=data['month'], attendance_period__year=data['year']).first()
        if period:
            input_rows = PayrollInput.objects.select_related('employee', 'period').filter(period=period, employee__in=scope)
            adjustments = PayrollAdjustment.objects.select_related('employee', 'period').filter(period=period, employee__in=scope).order_by('employee__code', 'kind', 'name')
            by_employee = {item.employee_id: item for item in input_rows}
            salary_statuses = dict(period.records.values_list('employee_id', 'status'))
            for employee in scope:
                item = by_employee.get(employee.pk)
                locked = period.status != 'pending' or salary_statuses.get(employee.pk) in ['approved', 'paid']
                state = 'locked' if locked else ('missing' if item is None else ('verified' if item.verified else 'draft'))
                counts['total'] += 1
                counts[state] += 1
                if data['readiness'] and data['readiness'] != state:
                    continue
                rates = [{'name': name, 'percent': Decimal(str(rate)) * 100} for name, rate in item.insurance_rates.items()] if item else []
                employee_rows.append({'employee': employee, 'input': item, 'locked': locked, 'state': state,
                    'state_label': {'missing': 'Chưa nhập', 'draft': 'Chưa kiểm tra', 'verified': 'Đã kiểm tra', 'locked': 'Đã khóa'}[state],
                    'rates': rates, 'salary_status': salary_statuses.get(employee.pk)})
            if data['readiness']:
                adjustments = adjustments.filter(employee_id__in=[row['employee'].pk for row in employee_rows])
            for item in adjustments:
                item.ui_locked = period.status != 'pending' or salary_statuses.get(item.employee_id) in ['approved', 'paid']
    return render(request, 'payroll/inputs.html', {'form': form, 'period': period, 'employee_rows': employee_rows,
        'inputs': input_rows, 'adjustments': adjustments, 'counts': counts,
        'month_label': str(form['month'].value()).zfill(2), 'year_label': form['year'].value()})


@login_required
def edit_input(request, kind, pk=None):
    require_role(request.user, HR, DIRECTOR)
    if kind not in ['tax', 'adjustment']:
        raise Http404
    model, form_class = (PayrollInput, PayrollInputForm) if kind == 'tax' else (PayrollAdjustment, AdjustmentForm)
    obj = get_object_or_404(model, pk=pk, employee__in=visible_employees(request.user)) if pk else None
    initial = {}
    if not obj and (request.GET.get('period') or request.GET.get('employee')):
        try:
            if request.GET.get('period'):
                initial['period'] = get_object_or_404(PayrollPeriod, pk=int(request.GET['period']), status='pending')
            if request.GET.get('employee'):
                initial['employee'] = get_object_or_404(visible_employees(request.user), pk=int(request.GET['employee']))
        except (ValueError, TypeError):
            raise Http404
    form = form_class(request.user, request.POST or None, instance=obj, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            value, changed = save_input(request.user, form.save(commit=False))
        except (ValidationError, IntegrityError) as exc:
            form.add_error(None, '; '.join(exc.messages) if isinstance(exc, ValidationError) else 'Dữ liệu bị trùng.')
        else:
            messages.success(request, 'Đã lưu dữ liệu. Chỉ cần tính lại lương nếu đầu vào tính lương thay đổi.' if changed else 'Dữ liệu không thay đổi.')
            at = value.period.attendance_period
            return redirect(reverse('payroll:inputs') + '?' + urlencode({'month': at.month, 'year': at.year}))
    selected_period = obj.period if obj else initial.get('period')
    back_query = urlencode({'month': selected_period.attendance_period.month, 'year': selected_period.attendance_period.year}) if selected_period else ''
    return render(request, 'payroll/input_form.html', {'form': form, 'kind': kind, 'locked': obj.is_locked if obj else False,
        'input_object': obj, 'back_query': back_query, 'title': 'Thuế và bảo hiểm theo kỳ' if kind == 'tax' else 'Phụ cấp / khấu trừ theo kỳ'})
