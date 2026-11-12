"""Nhận request, kiểm tra quyền và trả trang Bảng công; nghiệp vụ nằm trong services."""

from django.db.models import F
import csv
import io
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import IntegrityError
from django.db.models import Q
from django.core.paginator import Paginator
from django.http import HttpResponse, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from nhan_vien.access import visible_employees, require_role, has_role, HR, DIRECTOR, MANAGER
from nhan_vien.models import Employee
from .forms import AttendanceForm, AttendanceFilter
from .models import ChamCong, KyCong
from .services.workflow import save_record, change_period, approve_employee, record_is_locked
from .services.presentation import month_summary, month_data, audit_data, overtime_context


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
        period = KyCong.objects.filter(nam=data['year'], thang=data['month']).first()
        if data.get('day'):
            employees = employees.filter(is_active=True, hire_date__lte=data['day'])
            checked = ChamCong.objects.filter(ngay=data['day'], gio_vao__isnull=False)
            if data['day_state'] == 'unchecked':
                employees = employees.exclude(pk__in=checked.values(**{'employee_id': F('nhan_vien_id')}))
            elif data['day_state'] in ['ontime', 'late']:
                if period:
                    checked = checked.filter(gio_vao__lte=period.gio_bat_dau) if data['day_state'] == 'ontime' else checked.filter(gio_vao__gt=period.gio_bat_dau)
                    employees = employees.filter(pk__in=checked.values(**{'employee_id': F('nhan_vien_id')}))
                else:
                    employees = employees.none()
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
        'can_edit': not personal and has_role(request.user, HR, DIRECTOR) and (not context['period'] or context['period'].trang_thai != 'approved')
                    and (not context['summary'] or context['summary']['state'] != 'approved'),
        'can_approve': not personal and has_role(request.user, HR, DIRECTOR),
        'can_export': not personal and has_role(request.user, HR, DIRECTOR),
        'page_obj': Paginator(context['rows'], 6 if personal else 12).get_page(request.GET.get('page')),
        'page_query': page_query(request), 'director': has_role(request.user, DIRECTOR),
        'initials': ''.join(word[0] for word in employee.full_name.split()[-2:]).upper(),
        'tabs': [('', 'Tất cả'), ('late', 'Đi trễ'), ('leave', 'Nghỉ phép'), ('absent', 'Nghỉ không phép')]})
    return render(request, 'attendance/month.html', context)


@login_required
@require_POST
def approve_employee_view(request, employee_id, period_id):
    require_role(request.user, HR, DIRECTOR)
    employee = get_object_or_404(visible_employees(request.user), pk=employee_id)
    period = get_object_or_404(KyCong, pk=period_id)
    try:
        approval = approve_employee(request.user, employee, period.pk)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        messages.success(request, f'Đã duyệt bảng công của {employee.full_name} tháng {period}.')
        if getattr(approval, 'payroll_error', ''):
            messages.warning(request, 'Chưa đủ điều kiện cập nhật lương: ' + approval.payroll_error)
    return redirect(reverse('bang_cong:employee-month', args=[employee.pk]) + '?' +
                    urlencode({'month': period.thang, 'year': period.nam}))


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
        writer.writerow(['Mã NV', 'Họ tên', 'Ngày', 'Giờ vào', 'Giờ ra', 'Tình trạng', 'Phút muộn', 'Giờ làm', 'Công hưởng lương', 'Ghi chú','OT tự động (giờ)'])
        values = []
        for row in context['rows']:
            record = row['record']
            values.append([employee.code, employee.full_name, row['date'], record.gio_vao if record else '',
                record.gio_ra if record else '', row['label'], record.so_phut_tre if record else '',
                record.so_gio_lam if record else '', record.tong_cong if record else '', record.ghi_chu if record else '',row['ot']])
    for row in values:
        cells = [str(value) if value is not None else '' for value in row]
        writer.writerow(["'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value for value in cells])
    response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="attendance-{employee.pk}-{mode}.csv"'
    return response


@login_required
def detail(request, pk):
    row = get_object_or_404(ChamCong.objects.select_related('nhan_vien'), pk=pk,
                            nhan_vien__in=visible_employees(request.user))
    context={'row':row,'can_edit':has_role(request.user,HR,DIRECTOR) and not record_is_locked(row)}
    context.update(overtime_context(row))
    return render(request,'attendance/detail.html',context)


@login_required
def edit(request, pk=None):
    require_role(request.user, HR, DIRECTOR)
    row = get_object_or_404(ChamCong, pk=pk, nhan_vien__in=visible_employees(request.user)) if pk else None
    if row and record_is_locked(row):
        raise PermissionDenied('Kỳ công đã duyệt, không được chỉnh sửa chấm công.')
    initial = {'employee': request.GET.get('employee'), 'date': request.GET.get('date')} if not row else None
    form = AttendanceForm(request.user, request.POST or None, instance=row, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            saved = save_record(request.user, form.save(commit=False), form.cleaned_data['reason'])
        except KyCong.DoesNotExist:
            form.add_error(None, 'Chưa tạo kỳ công cho tháng này trong trang quản trị.')
        except ValidationError as exc:
            form.add_error(None, '; '.join(exc.messages))
        except IntegrityError:
            form.add_error(None, 'Đã có bản ghi nhân viên/ngày này hoặc dữ liệu không hợp lệ.')
        else:
            messages.success(request, 'Đã lưu và tính lại công.')
            return redirect('bang_cong:detail', pk=saved.pk)
    return render(request, 'attendance/edit.html', {'form': form, 'title': 'Ghi nhận / chỉnh sửa chấm công', 'row': row})


@login_required
@require_POST
def transition(request, pk):
    require_role(request.user, DIRECTOR)
    period = get_object_or_404(KyCong, pk=pk)
    try:
        change_period(request.user, pk, request.POST.get('action'), request.POST.get('reason', ''))
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    else:
        messages.success(request, 'Đã cập nhật trạng thái kỳ công.')
    return redirect(reverse('bang_cong:list') + '?' + urlencode({'month': period.thang, 'year': period.nam}))
