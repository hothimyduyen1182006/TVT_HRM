from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from employees.access import visible_employees, require_role, has_role, HR, DIRECTOR, MANAGER
from employees.models import Employee
from .forms import AttendanceForm, AttendanceFilter, DailyFilter, HistoryFilter
from .models import AttendanceRecord, AttendancePeriod, OvertimeApproval, AttendanceAuditLog
from .services.workflow import save_record, change_period, approve_employee
from .services.presentation import month_summary, daily_rows, history_logs, history_rows
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, Http404
from django.urls import reverse
from urllib.parse import urlencode
import csv
import io


@login_required
def record_list(request):
    if not has_role(request.user, HR, DIRECTOR, MANAGER):
        employee = visible_employees(request.user).first()
        if employee:
            return employee_month(request, employee.pk)
    form = AttendanceFilter(request.user, request.GET)
    rows = []
    period = None
    if form.is_valid():
        data = form.cleaned_data
        employees = form.employee_scope(request.user)
        if data['q']:
            employees = employees.filter(Q(full_name__icontains=data['q']) | Q(code__icontains=data['q']))
        period = AttendancePeriod.objects.filter(year=data['year'], month=data['month']).first()
        rows = month_summary(employees, data['year'], data['month'], period)
        if data['review']:
            rows = [row for row in rows if row['state'] == data['review']]
    page = Paginator(rows, 15).get_page(request.GET.get('page'))
    return render(request, 'attendance/list.html', {'form': form, 'rows': rows, 'period': period,
                  'page_obj': page, 'page_query': page_query(request),
                  'can_edit': has_role(request.user, HR, DIRECTOR), 'director': has_role(request.user, DIRECTOR)})


def page_query(request):
    values = request.GET.copy()
    values.pop('page', None)
    return values.urlencode()


def month_data(request, employee):
    form = DailyFilter(request.user, request.GET)
    rows, summary, period, progress, average = [], None, None, 0, '—'
    month_query = ''
    if form.is_valid():
        data = form.cleaned_data
        month_query = urlencode({'month': data['month'], 'year': data['year']})
        period = AttendancePeriod.objects.filter(year=data['year'], month=data['month']).first()
        summary = month_summary(Employee.objects.filter(pk=employee.pk), data['year'], data['month'], period)[0]
        rows = daily_rows(employee, data['year'], data['month'])
        work_count = sum(1 for row in rows if row['record'] and row['record'].check_in)
        if work_count:
            minutes = int(summary['hours'] * 60 / work_count)
            average = f'{minutes // 60}:{minutes % 60:02}'
        if summary['standard']:
            progress = max(0, min(100, int(summary['paid'] / summary['standard'] * 100)))
        if data['start']:
            rows = [r for r in rows if r['date'] >= data['start']]
        if data['end']:
            rows = [r for r in rows if r['date'] <= data['end']]
        if data['state']:
            state = data['state']
            unit_fields = {'paid': 'paid_units', 'actual': 'actual_units', 'paid_leave': 'paid_leave_units'}
            if state in unit_fields:
                rows = [r for r in rows if r['record'] and getattr(r['record'], unit_fields[state]) > 0]
            elif state == 'ot':
                rows = [r for r in rows if r['ot'] > 0]
            else:
                rows = [r for r in rows if r['state'] == state]
    stat_params = request.GET.copy()
    stat_params.pop('page', None)
    stat_params.pop('state', None)
    if form.is_valid():
        stat_params['month'] = form.cleaned_data['month']
        stat_params['year'] = form.cleaned_data['year']
    return {'form': form, 'rows': rows, 'summary': summary, 'period': period, 'progress': progress,
            'average': average, 'month_query': month_query, 'stat_query': stat_params.urlencode()}


@login_required
def personal(request):
    employee = get_object_or_404(Employee, user=request.user)
    return employee_month(request, employee.pk, own_only=True)


@login_required
def employee_month(request, employee_id, own_only=False):
    scope = Employee.objects.filter(user=request.user) if own_only else visible_employees(request.user)
    employee = get_object_or_404(scope, pk=employee_id)
    context = month_data(request, employee)
    personal = own_only or not has_role(request.user, HR, DIRECTOR, MANAGER)
    context.update({'employee': employee, 'personal': personal,
        'can_edit': not personal and has_role(request.user, HR, DIRECTOR) and (not context['period'] or context['period'].status != 'approved')
                    and (not context['summary'] or context['summary']['state'] != 'approved'),
        'can_approve': not personal and has_role(request.user, HR, DIRECTOR),
        'can_export': not personal and has_role(request.user, HR, DIRECTOR),
        'page_obj': Paginator(context['rows'], 6 if personal else 12).get_page(request.GET.get('page')),
        'page_query': page_query(request), 'director': has_role(request.user, DIRECTOR),
        'initials': ''.join(word[0] for word in employee.full_name.split()[-2:]).upper(),
        'tabs': [('', 'Tất cả'), ('late', 'Đi trễ'), ('leave', 'Nghỉ phép'), ('absent', 'Nghỉ không phép'), ('ot', 'Tăng ca')]})
    return render(request, 'attendance/month.html', context)


@login_required
@require_POST
def approve_employee_view(request, employee_id, period_id):
    require_role(request.user, HR, DIRECTOR)
    employee = get_object_or_404(visible_employees(request.user), pk=employee_id)
    period = get_object_or_404(AttendancePeriod, pk=period_id)
    try:
        approve_employee(request.user, employee, period.pk)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        messages.success(request, f'Đã duyệt bảng công của {employee.full_name} tháng {period}.')
    return redirect(reverse('attendance:employee-month', args=[employee.pk]) + '?' +
                    urlencode({'month': period.month, 'year': period.year}))


def audit_data(request, employee):
    period_form = AttendanceFilter(request.user, request.GET)
    logs = AttendanceAuditLog.objects.none()
    month_query = ''
    if period_form.is_valid():
        data = period_form.cleaned_data
        month_query = urlencode({'month': data['month'], 'year': data['year']})
        logs = history_logs(employee, data['year'], data['month'])
    form = HistoryFilter(request.GET, logs)
    rows = []
    if form.is_valid() and period_form.is_valid():
        data = form.cleaned_data
        if data['start']:
            logs = logs.filter(created_at__date__gte=data['start'])
        if data['end']:
            logs = logs.filter(created_at__date__lte=data['end'])
        if data['actor']:
            logs = logs.filter(actor=data['actor'])
        rows = history_rows(logs, data['field'])
    return {'form': form, 'period_form': period_form, 'rows': rows, 'month_query': month_query}


@login_required
def history(request, employee_id):
    scope = Employee.objects.filter(Q(pk__in=visible_employees(request.user).values('pk')) | Q(user=request.user))
    employee = get_object_or_404(scope, pk=employee_id)
    context = audit_data(request, employee)
    context.update({'employee': employee, 'can_export': has_role(request.user, HR, DIRECTOR),
        'page_obj': Paginator(context['rows'], 20).get_page(request.GET.get('page')), 'page_query': page_query(request)})
    return render(request, 'attendance/history.html', context)


@login_required
def export_month(request, employee_id):
    require_role(request.user, HR, DIRECTOR)
    employee = get_object_or_404(visible_employees(request.user), pk=employee_id)
    mode = request.GET.get('mode', 'month')
    if mode not in ['month', 'history']:
        raise Http404
    context = audit_data(request, employee) if mode == 'history' else month_data(request, employee)
    if not context['form'].is_valid() or (mode == 'history' and not context['period_form'].is_valid()):
        return HttpResponse('Bộ lọc không hợp lệ.', status=400)
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    if mode == 'history':
        writer.writerow(['Thời gian điều chỉnh', 'Ngày công', 'Trường', 'Giá trị cũ', 'Giá trị mới', 'Người sửa', 'Lý do'])
        values = [[r['time'].isoformat(), r['date'], r['field'], r['old'], r['new'], r['actor'], r['reason']]
                  for r in context['rows']]
    else:
        writer.writerow(['Mã NV', 'Họ tên', 'Ngày', 'Giờ vào', 'Giờ ra', 'Tình trạng', 'Phút muộn', 'Giờ làm', 'OT duyệt', 'Công hưởng lương', 'Ghi chú'])
        values = []
        for row in context['rows']:
            record = row['record']
            values.append([employee.code, employee.full_name, row['date'], record.check_in if record else '',
                record.check_out if record else '', row['label'], record.late_minutes if record else '',
                record.work_hours if record else '', row['ot'], record.paid_units if record else '', record.note if record else ''])
    for row in values:
        cells = [str(value) if value is not None else '' for value in row]
        writer.writerow(["'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value for value in cells])
    response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="attendance-{employee.pk}-{mode}.csv"'
    return response


@login_required
def detail(request, pk):
    row = get_object_or_404(AttendanceRecord.objects.select_related('employee'), pk=pk,
                            employee__in=visible_employees(request.user))
    overtime = OvertimeApproval.objects.filter(employee=row.employee, date=row.date, approved=True,
                                               approved_by__isnull=False, approved_at__isnull=False)
    return render(request, 'attendance/detail.html', {'row': row, 'overtime': overtime,
                  'can_edit': has_role(request.user, HR, DIRECTOR)})


@login_required
def edit(request, pk=None):
    require_role(request.user, HR, DIRECTOR)
    row = get_object_or_404(AttendanceRecord, pk=pk, employee__in=visible_employees(request.user)) if pk else None
    initial = {'employee': request.GET.get('employee'), 'date': request.GET.get('date')} if not row else None
    form = AttendanceForm(request.user, request.POST or None, instance=row, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            saved = save_record(request.user, form.save(commit=False), form.cleaned_data['reason'])
        except AttendancePeriod.DoesNotExist:
            form.add_error(None, 'Chưa tạo kỳ công cho tháng này trong trang quản trị.')
        except ValidationError as exc:
            form.add_error(None, '; '.join(exc.messages))
        except IntegrityError:
            form.add_error(None, 'Đã có bản ghi nhân viên/ngày này hoặc dữ liệu không hợp lệ.')
        else:
            messages.success(request, 'Đã lưu và tính lại công.')
            return redirect('attendance:detail', pk=saved.pk)
    return render(request, 'attendance/edit.html', {'form': form, 'title': 'Ghi nhận / chỉnh sửa chấm công', 'row': row})


@login_required
@require_POST
def transition(request, pk):
    require_role(request.user, DIRECTOR)
    period = get_object_or_404(AttendancePeriod, pk=pk)
    try:
        change_period(request.user, pk, request.POST.get('action'), request.POST.get('reason', ''))
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        messages.success(request, 'Đã cập nhật trạng thái kỳ công.')
    return redirect(reverse('attendance:list') + '?' + urlencode({'month': period.month, 'year': period.year}))
