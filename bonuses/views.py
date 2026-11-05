import calendar
import csv
import io
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from attendance.models import AttendanceRecord, AttendancePeriod, WorkCalendarDay
from employees.access import DIRECTOR, HR, MANAGER, has_role, require_role, visible_employees
from leaves.models import LeaveDay
from .forms import BonusFilter, BonusProposalForm, PersonalBonusFilter
from .models import Bonus


def bonus_rows(user, form):
    if not form.is_valid():
        return Bonus.objects.none()
    data = form.cleaned_data
    rows = Bonus.objects.select_related('employee__department', 'proposed_by', 'approved_by').filter(
        employee__in=form.employee_scope(user), month=data['month'], year=data['year'])
    if has_role(user, DIRECTOR):
        rows = rows.exclude(status='draft')
    if data.get('q'):
        rows = rows.filter(Q(employee__full_name__icontains=data['q']) | Q(employee__code__icontains=data['q']))
    return rows.order_by('employee__code', 'bonus_type', 'name')


def grouped_bonuses(rows):
    groups = {}
    for bonus in rows:
        key = (bonus.employee_id, bonus.year, bonus.month)
        if key not in groups:
            groups[key] = {'employee': bonus.employee, 'year': bonus.year, 'month': bonus.month,
                'attendance': Decimal(0), 'seniority': Decimal(0), 'other': Decimal(0),
                'items': [], 'records': [], 'statuses': set(), 'approved_at': bonus.approved_at,
                'rejection_reason': bonus.rejection_reason}
        group = groups[key]
        group['records'].append(bonus)
        group['statuses'].add(bonus.status)
        group['approved_at'] = max(filter(None, [group['approved_at'], bonus.approved_at]), default=None)
        group['rejection_reason'] = group['rejection_reason'] or bonus.rejection_reason
        group[bonus.bonus_type] += bonus.amount
        if bonus.bonus_type == 'other':
            group['items'].append(bonus)
    results = []
    for (employee_id, year, month), group in groups.items():
        order = {'seniority': 0, 'attendance': 1, 'other': 2}
        group['records'].sort(key=lambda item: (order.get(item.bonus_type, 9), item.name))
        statuses = group['statuses']
        group['status'] = ('pending' if 'pending' in statuses else 'draft' if 'draft' in statuses else
                           'rejected' if 'rejected' in statuses else 'approved')
        group['total'] = group['attendance'] + group['seniority'] + group['other']
        group['employee_id'] = employee_id
        group['has_pending'] = 'pending' in statuses
        group['has_draft'] = 'draft' in statuses
        results.append(group)
    return sorted(results, key=lambda row: (row['employee'].code, -row['year'], -row['month']))


@login_required
def bonus_list(request):
    if not has_role(request.user, HR, DIRECTOR, MANAGER):
        return personal_list(request)
    form = BonusFilter(request.user, request.GET)
    rows = grouped_bonuses(bonus_rows(request.user, form))
    if form.is_valid() and form.cleaned_data.get('status'):
        rows = [row for row in rows if row['status'] == form.cleaned_data['status']]
    total_amount = sum((row['total'] for row in rows), Decimal(0))
    return render(request, 'bonuses/list.html', {'form': form, 'rows': rows,
        'total_amount': total_amount,
        'can_propose': has_role(request.user, HR, MANAGER),
        'can_submit': has_role(request.user, HR), 'can_review': has_role(request.user, DIRECTOR),
        'can_export': has_role(request.user, HR, DIRECTOR)})


@login_required
def personal_list(request):
    form = PersonalBonusFilter(request.GET)
    rows = Bonus.objects.select_related('employee__department').filter(
        employee__user=request.user, status='approved').order_by('-year', '-month', 'name')
    if form.is_valid():
        if form.cleaned_data.get('month'):
            rows = rows.filter(month=form.cleaned_data['month'])
        if form.cleaned_data.get('year'):
            rows = rows.filter(year=form.cleaned_data['year'])
    grouped = grouped_bonuses(rows)
    return render(request, 'bonuses/personal.html', {'form': form, 'rows': grouped,
        'total_amount': sum((row['total'] for row in grouped), Decimal(0)),
        'can_manage': has_role(request.user, HR, DIRECTOR, MANAGER)})


def calculate_automatic(employee, month, year):
    start, end = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    period = AttendancePeriod.objects.filter(month=month, year=year).first()
    workdays = WorkCalendarDay.objects.filter(date__range=(max(start, employee.hire_date), end),
                                               kind='work', expected_units__gt=0)
    if not period or not workdays.exists():
        raise ValidationError('Thiếu dữ liệu chấm công hoặc lịch làm việc của kỳ thưởng.')
    approved = period.status == 'approved' or period.employee_approvals.filter(employee=employee).exists()
    if not approved:
        raise ValidationError(f'Bảng công của {employee} chưa được duyệt.')
    records = {record.date: record for record in AttendanceRecord.objects.filter(employee=employee, date__range=(start, end))}
    leave_dates = set(LeaveDay.objects.filter(employee=employee, date__range=(start, end), approved=True).values_list('date', flat=True))
    if any(day.date not in records and day.date not in leave_dates for day in workdays):
        raise ValidationError(f'Thiếu dữ liệu chấm công của {employee}.')
    day_records = [records[d.date] for d in workdays if d.date in records]
    if any(record.status == 'absent' for record in day_records):
        attendance_amount, attendance_reason = Decimal(0), 'Có ngày nghỉ không phép trong kỳ.'
    elif any(record.status == 'incomplete' for record in day_records):
        raise ValidationError(f'Dữ liệu chấm công của {employee} chưa đầy đủ.')
    elif any(record.late_minutes for record in day_records):
        attendance_amount, attendance_reason = Decimal(0), 'Không đạt điều kiện chuyên cần do có đi muộn.'
    elif leave_dates.intersection(day.date for day in workdays) or any(r.status == 'leave' for r in day_records):
        attendance_amount, attendance_reason = Decimal(200000), 'Có nghỉ phép hợp lệ trong kỳ.'
    else:
        attendance_amount, attendance_reason = Decimal(500000), 'Đủ ngày công quy định trong tháng.'
    period_end = end
    years = max(0, period_end.year - employee.hire_date.year -
                ((period_end.month, period_end.day) < (employee.hire_date.month, employee.hire_date.day)))
    rate = Decimal(0) if years < 1 else Decimal(150000) if years < 3 else Decimal(200000) if years < 5 else Decimal(500000)
    seniority_amount = years * rate
    seniority_reason = f'{years} năm thâm niên; mức thưởng tháng áp dụng {rate:,.0f} VNĐ.'
    return [("attendance", "Thưởng chuyên cần", attendance_amount, attendance_reason),
            ("seniority", "Thưởng thâm niên", seniority_amount, seniority_reason)]


@login_required
def detail(request, employee_id, year, month):
    employee = get_object_or_404(visible_employees(request.user), pk=employee_id)
    rows = Bonus.objects.select_related('employee__department', 'proposed_by', 'approved_by').filter(
        employee=employee, year=year, month=month)
    if not has_role(request.user, HR, DIRECTOR, MANAGER):
        rows = rows.filter(status='approved')
    elif has_role(request.user, DIRECTOR) and not has_role(request.user, HR):
        rows = rows.exclude(status='draft')
    grouped = grouped_bonuses(rows)
    if not grouped:
        from django.http import Http404
        raise Http404
    group = grouped[0]
    existing_types = {item.bonus_type for item in group['records']}
    display_records = [{
        'type_label': item.get_bonus_type_display(), 'name': item.name, 'bonus_type': item.bonus_type,
        'amount': item.amount, 'reason': item.reason, 'proposed_at': item.proposed_at,
        'is_uncomputed': False,
    } for item in group['records']]
    group['total_complete'] = True
    missing_types = {'attendance', 'seniority'} - existing_types
    if missing_types:
        try:
            computed = calculate_automatic(employee, month, year)
        except ValidationError as exc:
            group['total_complete'] = False
            unavailable_reason = '; '.join(exc.messages)
            labels = {'seniority': 'Thưởng thâm niên', 'attendance': 'Thưởng chuyên cần'}
            for bonus_type in missing_types:
                display_records.append({'type_label': labels[bonus_type], 'name': labels[bonus_type],
                    'bonus_type': bonus_type, 'amount': None, 'reason': unavailable_reason,
                    'proposed_at': None, 'is_uncomputed': True})
        else:
            for bonus_type, name, amount, reason in computed:
                if bonus_type in missing_types:
                    group[bonus_type] = amount
                    group['total'] += amount
                    display_records.append({'type_label': name, 'name': name, 'bonus_type': bonus_type,
                        'amount': amount, 'reason': reason, 'proposed_at': None, 'is_uncomputed': False})
    order = {'seniority': 0, 'attendance': 1, 'other': 2}
    group['records'] = sorted(display_records, key=lambda item: order.get(item['bonus_type'], 9))
    group['can_submit'] = has_role(request.user, HR) and group['has_draft']
    group['can_decide'] = has_role(request.user, DIRECTOR) and group['has_pending']
    return render(request, 'bonuses/detail.html', {'row': group})


@login_required
def propose(request):
    if has_role(request.user, DIRECTOR) and not has_role(request.user, HR, MANAGER):
        messages.info(request, 'Giám đốc không lập đề xuất. Hãy mở bảng thưởng đang Chờ duyệt và chọn Xem chi tiết để duyệt hoặc từ chối.')
        return redirect('bonuses:list')
    require_role(request.user, HR, MANAGER)
    form = BonusProposalForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        try:
            state = 'draft'
            with transaction.atomic():
                locked_rows = Bonus.objects.filter(employee=data['employee'], month=data['month'], year=data['year'],
                    status__in=['pending', 'approved'])
                if locked_rows.exists():
                    raise ValidationError('Kỳ thưởng đã gửi duyệt hoặc đã duyệt, không thể lập lại.')
                previous = Bonus.objects.filter(employee=data['employee'], month=data['month'], year=data['year'],
                    bonus_type='other', name=data['name'], status='rejected').first()
                values = {'reason': data['reason'], 'amount': data['amount'], 'proposed_by': request.user,
                          'proposed_at': timezone.now(), 'status': state, 'rejection_reason': ''}
                if previous:
                    Bonus.objects.filter(pk=previous.pk).update(**values)
                else:
                    Bonus.objects.create(employee=data['employee'], month=data['month'], year=data['year'],
                        bonus_type='other', name=data['name'], **values)
        except ValidationError as exc:
            form.add_error(None, '; '.join(exc.messages))
        else:
            messages.success(request, 'Gửi đề xuất thành công. Đề xuất thưởng khác đang chờ QLNS kiểm tra.')
            return redirect('bonuses:list')
    history = grouped_bonuses(Bonus.objects.select_related('employee__department').filter(
        employee__in=visible_employees(request.user), proposed_by=request.user).order_by('-year', '-month'))
    return render(request, 'bonuses/propose.html', {'form': form, 'history': history})


@login_required
@require_POST
def calculate_period(request):
    require_role(request.user, HR)
    form = BonusFilter(request.user, request.POST)
    if not form.is_valid():
        messages.error(request, 'Vui lòng chọn kỳ thưởng hợp lệ trước khi tính tự động.')
        return redirect('bonuses:list')
    data = form.cleaned_data
    employees = form.employee_scope(request.user)
    if data.get('q'):
        employees = employees.filter(Q(full_name__icontains=data['q']) | Q(code__icontains=data['q']))
    created, locked, errors = 0, 0, []
    for employee in employees:
        if Bonus.objects.filter(employee=employee, month=data['month'], year=data['year'],
                                status__in=['pending', 'approved']).exists():
            locked += 1
            continue
        try:
            automatic = calculate_automatic(employee, data['month'], data['year'])
            with transaction.atomic():
                for bonus_type, name, amount, reason in automatic:
                    Bonus.objects.update_or_create(employee=employee, month=data['month'], year=data['year'],
                        bonus_type=bonus_type, defaults={'name': name, 'amount': amount, 'reason': reason,
                        'proposed_by': request.user, 'proposed_at': timezone.now(), 'status': 'draft',
                        'rejection_reason': ''})
            created += 1
        except ValidationError as exc:
            errors.append(f'{employee.code}: {"; ".join(exc.messages)}')
    if created:
        messages.success(request, f'Đã tính thưởng tự động cho {created} nhân viên; QLNS có thể kiểm tra và gửi duyệt.')
    if locked:
        messages.info(request, f'Bỏ qua {locked} nhân viên đã có thưởng chờ duyệt hoặc đã duyệt.')
    if errors:
        messages.warning(request, 'Chưa tính được: ' + ' | '.join(errors[:5]))
    if not created and not locked and not errors:
        messages.info(request, 'Không có nhân viên trong phạm vi lọc để tính thưởng.')
    return redirect('bonuses:list')


@login_required
@require_POST
def submit(request, employee_id, year, month):
    require_role(request.user, HR)
    get_object_or_404(visible_employees(request.user), pk=employee_id)
    count = Bonus.objects.filter(employee_id=employee_id, year=year, month=month, status='draft').update(status='pending')
    if not count:
        messages.error(request, 'Không có đề xuất nháp trong kỳ này để gửi duyệt.')
        return redirect('bonuses:list')
    messages.success(request, 'Đã gửi bảng thưởng tổng hợp chờ Giám đốc duyệt.')
    return redirect('bonuses:list')


@login_required
@require_POST
def decision(request, employee_id, year, month):
    require_role(request.user, DIRECTOR)
    rows = Bonus.objects.filter(employee_id=employee_id, year=year, month=month, status='pending')
    if not rows.exists():
        from django.http import Http404
        raise Http404
    action = request.POST.get('action')
    if action not in ['approve', 'reject']:
        raise ValidationError('Lựa chọn duyệt không hợp lệ.')
    reason = request.POST.get('reason', '').strip()
    if action == 'reject' and not reason:
        messages.error(request, 'Vui lòng nhập lý do từ chối.')
        return redirect('bonuses:list')
    rows.update(status='approved' if action == 'approve' else 'rejected', approved_by=request.user,
                approved_at=timezone.now(), rejection_reason=reason if action == 'reject' else '')
    messages.success(request, 'Đã cập nhật kết quả duyệt thưởng.')
    return redirect('bonuses:list')


@login_required
@require_POST
def export(request):
    require_role(request.user, HR, DIRECTOR)
    form = BonusFilter(request.user, request.POST)
    if not form.is_valid():
        messages.error(request, 'Bộ lọc không hợp lệ.')
        return redirect('bonuses:list')
    form.cleaned_data['status'] = ''
    rows = bonus_rows(request.user, form)
    rows = rows.filter(status='approved')
    if not rows.exists():
        messages.error(request, 'Chưa có dữ liệu thưởng đã duyệt để xuất.')
        return redirect('bonuses:list')
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['Mã nhân viên', 'Nhân viên', 'Phòng ban', 'Tháng', 'Năm', 'Loại thưởng', 'Khoản thưởng', 'Lý do', 'Số tiền', 'Trạng thái'])
    for row in rows:
        writer.writerow([row.employee.code, row.employee.full_name, row.employee.department.name, row.month, row.year,
                         row.get_bonus_type_display(), row.name, row.reason, row.amount, row.get_status_display()])
    response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
    data = form.cleaned_data
    response['Content-Disposition'] = f'attachment; filename="bonuses-{data["month"]}-{data["year"]}.csv"'
    return response
