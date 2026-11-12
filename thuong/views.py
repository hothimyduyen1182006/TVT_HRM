import calendar
import csv
import io
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from bang_cong.models import ChamCong, KyCong, LichLamViec
from nhan_vien.access import DIRECTOR, HR, MANAGER, has_role, visible_employees
from nhan_vien.models import Employee
from nghi_phep.models import LeaveDay
from .forms import BonusFilter, BonusProposalForm, PersonalBonusFilter
from .models import Bonus, approved_bonus_records, complete_bonus_records, displayed_bonus_records


def access_denied(request):
    return render(request, 'bonuses/access_denied.html', status=403)


def bonus_rows(user, form):
    if not form.is_valid():
        return Bonus.objects.none()
    data = form.cleaned_data
    rows = displayed_bonus_records(
        Bonus.objects.select_related(
            'employee__department', 'proposed_by', 'approved_by'
        ).filter(employee__in=form.employee_scope(user))
    )
    if data.get('month'):
        rows = rows.filter(month=data['month'])
    if data.get('year'):
        rows = rows.filter(year=data['year'])
    if has_role(user, DIRECTOR):
        rows = rows.exclude(status='draft')
    if data.get('q'):
        rows = rows.filter(
            Q(employee__full_name__icontains=data['q'])
            | Q(employee__code__icontains=data['q'])
        )
    return rows.order_by('employee__code', 'bonus_type', 'name')


def grouped_bonuses(rows):
    groups = {}
    for bonus in rows:
        key = (bonus.employee_id, bonus.year, bonus.month)
        if key not in groups:
            groups[key] = {
                'employee': bonus.employee,
                'year': bonus.year,
                'month': bonus.month,
                'attendance': Decimal(0),
                'seniority': Decimal(0),
                'other': Decimal(0),
                'items': [],
                'records': [],
                'statuses': set(),
                'approved_at': bonus.approved_at,
                'rejection_reason': bonus.rejection_reason,
            }
        group = groups[key]
        group['records'].append(bonus)
        group['statuses'].add(bonus.status)
        group['approved_at'] = max(
            filter(None, [group['approved_at'], bonus.approved_at]), default=None
        )
        group['rejection_reason'] = group['rejection_reason'] or bonus.rejection_reason
        group[bonus.bonus_type] += bonus.amount
        if bonus.bonus_type == 'other':
            group['items'].append(bonus)
    results = []
    for (employee_id, year, month), group in groups.items():
        order = {'seniority': 0, 'attendance': 1, 'other': 2}
        group['records'].sort(key=lambda item: (order.get(item.bonus_type, 9), item.name))
        statuses = group['statuses']
        group['status'] = (
            'pending' if 'pending' in statuses else
            'draft' if 'draft' in statuses else
            'rejected' if 'rejected' in statuses else
            'approved'
        )
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
    form = BonusFilter(request.user, request.GET, default_current_period=True)
    if not form.is_valid() and {'employee', 'department'} & set(form.errors):
        return access_denied(request)
    source_rows = bonus_rows(request.user, form)
    rows = grouped_bonuses(source_rows)
    if form.is_valid() and form.cleaned_data.get('status'):
        rows = [row for row in rows if row['status'] == form.cleaned_data['status']]
    total_amount = sum((row['total'] for row in rows), Decimal(0))
    page_query = request.GET.copy()
    page_query.pop('page', None)
    page_obj = Paginator(rows, 5).get_page(request.GET.get('page'))
    return render(request, 'bonuses/list_redesign.html', {
        'form': form,
        'page_obj': page_obj,
        'rows': page_obj.object_list,
        'page_query': page_query.urlencode(),
        'total_amount': total_amount,
        'can_propose': has_role(request.user, HR, MANAGER),
        'can_submit': has_role(request.user, HR),
        'can_review': has_role(request.user, DIRECTOR),
        'can_export': has_role(request.user, HR, DIRECTOR),
    })


@login_required
def personal_list(request):
    employee = Employee.objects.filter(user=request.user).first()
    if employee is None and not has_role(request.user, HR, DIRECTOR, MANAGER):
        return access_denied(request)

    form = PersonalBonusFilter(request.GET)
    rows = displayed_bonus_records(Bonus.objects.select_related('employee__department').filter(
        employee__user=request.user)).order_by('-year', '-month', 'name')
    month = year = status = None
    if form.is_valid():
        month = form.cleaned_data.get('month')
        year = form.cleaned_data.get('year')
        status = form.cleaned_data.get('status')
        if month:
            rows = rows.filter(month=month)
        if year:
            rows = rows.filter(year=year)
        if status:
            rows = rows.filter(status=status)
    all_rows = displayed_bonus_records(Bonus.objects.filter(employee__user=request.user))
    received_rows = all_rows.filter(status='approved')
    if year:
        received_rows = received_rows.filter(year=year)
    pending_rows = all_rows.filter(status='pending')
    total_received = received_rows.aggregate(total=Sum('amount'))['total'] or Decimal(0)
    pending_total = pending_rows.aggregate(total=Sum('amount'))['total'] or Decimal(0)
    summary_total = rows.aggregate(total=Sum('amount'))['total'] or Decimal(0)
    received_label = f'Tổng đã nhận (Năm {year})' if year else 'Tổng đã nhận (Tất cả năm)'
    if month and year:
        summary_label = f'Thưởng tháng {month}/{year}'
    elif year:
        summary_label = f'Thưởng năm {year}'
    elif month:
        summary_label = f'Thưởng tháng {month}'
    else:
        summary_label = 'Tổng thưởng theo bộ lọc'
    grouped = grouped_bonuses(rows)
    return render(request, 'bonuses/personal.html', {'form': form, 'rows': grouped,
        'total_amount': sum((row['total'] for row in grouped), Decimal(0)),
        'total_received': total_received, 'pending_total': pending_total,
        'summary_total': summary_total, 'received_label': received_label,
        'summary_label': summary_label,
        'employee': employee,
        'personal': True})


def calculate_seniority(employee, month, year):
    period_end = date(year, month, calendar.monthrange(year, month)[1])
    years = max(0, period_end.year - employee.hire_date.year -
                ((period_end.month, period_end.day) < (employee.hire_date.month, employee.hire_date.day)))
    rate = Decimal(0) if years < 1 else Decimal(150000) if years < 3 else Decimal(200000) if years < 5 else Decimal(500000)
    amount = years * rate
    reason = f'{years} năm thâm niên; mức thưởng tháng áp dụng {rate:,.0f} VNĐ.'
    return "seniority", "Thưởng thâm niên", amount, reason


def calculate_attendance(employee, month, year):
    start, end = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    period = KyCong.objects.filter(thang=month, nam=year).first()
    workdays = LichLamViec.objects.filter(ngay__range=(max(start, employee.hire_date), end),
                                               loai_ngay='work', cong_chuan__gt=0)
    if not period or not workdays.exists():
        raise ValidationError('Thiếu dữ liệu chấm công hoặc lịch làm việc của kỳ thưởng.')
    approved = True  # Use complete attendance inputs; approval is not a UC 6.2 eligibility rule.
    if not approved:
        raise ValidationError(f'Bảng công của {employee} chưa được duyệt.')
    records = {record.ngay: record for record in ChamCong.objects.filter(nhan_vien=employee, ngay__range=(start, end))}
    leave_dates = set(LeaveDay.objects.filter(employee=employee, date__range=(start, end), approved=True).values_list('date', flat=True))
    if any(day.ngay not in records and day.ngay not in leave_dates for day in workdays):
        raise ValidationError(f'Thiếu dữ liệu chấm công của {employee}.')
    day_records = [records[d.ngay] for d in workdays if d.ngay in records]
    if any(record.trang_thai == 'absent' or
           (record.trang_thai == 'leave' and record.ngay not in leave_dates)
           for record in day_records):
        attendance_amount, attendance_reason = Decimal(0), 'Có ngày nghỉ không phép trong kỳ.'
    elif any(record.trang_thai == 'incomplete' for record in day_records):
        raise ValidationError(f'Dữ liệu chấm công của {employee} chưa đầy đủ.')
    elif any(record.so_phut_tre for record in day_records) or any(
            record.gio_ra and record.gio_ra < period.gio_ket_thuc and record.ngay not in leave_dates
            for record in day_records):
        attendance_amount, attendance_reason = Decimal(0), 'Không đạt điều kiện chuyên cần do đi muộn hoặc về sớm vượt ngưỡng.'
    elif leave_dates.intersection(day.ngay for day in workdays):
        attendance_amount, attendance_reason = Decimal(200000), 'Có nghỉ phép hợp lệ trong kỳ.'
    else:
        attendance_amount, attendance_reason = Decimal(500000), 'Đủ ngày công quy định trong tháng.'
    return "attendance", "Thưởng chuyên cần", attendance_amount, attendance_reason


def calculate_automatic(employee, month, year):
    results = [calculate_seniority(employee, month, year)]
    try:
        results.append(calculate_attendance(employee, month, year))
    except ValidationError as exc:
        return results, exc
    return results, None


def ensure_automatic_bonuses(employee, month, year, actor):
    """Create or refresh editable automatic bonus rows from approved source data."""
    automatic, _ = calculate_automatic(employee, month, year)
    for bonus_type, name, amount, reason in automatic:
        row = Bonus.objects.filter(employee=employee, month=month, year=year,
                                   bonus_type=bonus_type).first()
        if row and row.status in ('pending', 'approved'):
            continue
        now = timezone.now()
        if row:
            changed = any((row.name != name, row.amount != amount, row.reason != reason,
                           row.status != 'draft', bool(row.rejection_reason)))
            if not changed:
                continue
            row.name, row.amount, row.reason = name, amount, reason
            row.proposed_by, row.proposed_at = actor, now
            row.status, row.rejection_reason = 'draft', ''
            row.save(update_fields=['name', 'amount', 'reason', 'proposed_by', 'proposed_at',
                                    'status', 'rejection_reason'])
        else:
            Bonus.objects.create(employee=employee, month=month, year=year, bonus_type=bonus_type,
                name=name, amount=amount, reason=reason, proposed_by=actor, proposed_at=now,
                status='draft')


@login_required
def detail(request, employee_id, year, month):
    if (Employee.objects.filter(pk=employee_id).exists()
            and not visible_employees(request.user).filter(pk=employee_id).exists()):
        return access_denied(request)
    employee = get_object_or_404(visible_employees(request.user), pk=employee_id)
    rows = displayed_bonus_records(Bonus.objects.select_related(
        'employee__department', 'proposed_by', 'approved_by').filter(
            employee=employee, year=year, month=month))
    is_own_profile = employee.user_id == request.user.id
    if not is_own_profile and not has_role(request.user, HR, DIRECTOR, MANAGER):
        rows = rows.filter(status='approved')
    elif not is_own_profile and has_role(request.user, DIRECTOR) and not has_role(request.user, HR):
        rows = rows.exclude(status='draft')
    grouped = grouped_bonuses(rows)
    if not grouped:
        raise Http404
    group = grouped[0]
    needs_auto_reason = any(
        item.bonus_type in {'attendance', 'seniority'} and not item.reason
        for item in group['records']
    )
    automatic, attendance_error = (calculate_automatic(employee, month, year)
                                   if needs_auto_reason else ([], None))
    automatic_reasons = {bonus_type: reason for bonus_type, _name, _amount, reason in automatic}
    if attendance_error and 'attendance' not in automatic_reasons:
        automatic_reasons['attendance'] = '; '.join(attendance_error.messages)
    display_records = [{
        'id': item.pk,
        'type_label': (item.name if item.bonus_type == 'other' else item.get_bonus_type_display()),
        'name': item.name, 'bonus_type': item.bonus_type,
        'amount': item.amount,
        'reason': item.reason or automatic_reasons.get(item.bonus_type, ''),
        'proposed_at': item.proposed_at,
        'is_uncomputed': False,
        'can_edit': (item.bonus_type == 'other' and item.status == 'rejected'
                     and has_role(request.user, HR, MANAGER)),
        'can_delete': (item.bonus_type == 'other' and item.status in {'draft', 'pending', 'rejected'}
                       and has_role(request.user, HR, MANAGER)),
    } for item in group['records']]
    group['total_complete'] = True
    order = {'seniority': 0, 'attendance': 1, 'other': 2}
    group['records'] = sorted(display_records, key=lambda item: order.get(item['bonus_type'], 9))
    group['can_submit'] = has_role(request.user, HR, MANAGER) and group['has_draft']
    group['can_decide'] = has_role(request.user, DIRECTOR) and group['has_pending']
    return render(request, 'bonuses/detail.html', {'row': group})


@login_required
def propose(request):
    if has_role(request.user, DIRECTOR) and not has_role(request.user, HR, MANAGER):
        return access_denied(request)
    if not has_role(request.user, HR, MANAGER):
        return access_denied(request)
    form = BonusProposalForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        try:
            with transaction.atomic():
                locked_rows = complete_bonus_records(Bonus.objects.filter(
                    employee=data['employee'], month=data['month'], year=data['year'],
                    bonus_type='other', name=data['name'], status__in=['pending', 'approved']))
                if locked_rows.exists():
                    raise ValidationError('Khoản thưởng cùng tên trong kỳ này đang chờ duyệt hoặc đã được duyệt.')
                previous = Bonus.objects.filter(employee=data['employee'], month=data['month'], year=data['year'],
                    bonus_type='other', name=data['name'], status='rejected').first()
                values = {'reason': data['reason'], 'amount': data['amount'], 'proposed_by': request.user,
                          'proposed_at': timezone.now(), 'status': 'pending', 'rejection_reason': '',
                          'approved_by': None, 'approved_at': None}
                if previous:
                    Bonus.objects.filter(pk=previous.pk).update(**values)
                else:
                    Bonus.objects.create(employee=data['employee'], month=data['month'], year=data['year'],
                        bonus_type='other', name=data['name'], **values)
        except ValidationError as exc:
            form.add_error(None, '; '.join(exc.messages))
        else:
            messages.success(request, 'Đã gửi đề xuất thưởng, đang chờ Giám đốc duyệt.')
            return redirect('thuong:propose')
    history = complete_bonus_records(Bonus.objects.select_related('employee__department').filter(
        employee__in=visible_employees(request.user), proposed_by=request.user,
        bonus_type='other')).order_by('-proposed_at', '-pk')
    return render(request, 'bonuses/propose.html', {'form': form, 'history': history})


@login_required
def edit_rejected_proposal(request, bonus_id):
    if not has_role(request.user, HR, MANAGER):
        return access_denied(request)

    editable_rows = complete_bonus_records(Bonus.objects.filter(
        pk=bonus_id, bonus_type='other', status='rejected',
        employee__in=visible_employees(request.user)))
    bonus = get_object_or_404(editable_rows)
    initial = {
        'month': bonus.month,
        'year': bonus.year,
        'employee': bonus.employee_id,
        'name': bonus.name,
        'reason': bonus.reason,
        'amount': bonus.amount,
    }
    form = BonusProposalForm(request.user, request.POST or None, initial=initial)
    for field_name in ('month', 'year', 'employee'):
        form.fields[field_name].disabled = True

    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        try:
            with transaction.atomic():
                bonus = get_object_or_404(complete_bonus_records(Bonus.objects.select_for_update().filter(
                    pk=bonus_id, bonus_type='other', status='rejected',
                    employee__in=visible_employees(request.user))))
                bonus.name = data['name']
                bonus.reason = data['reason']
                bonus.amount = data['amount']
                bonus.proposed_by = request.user
                bonus.proposed_at = timezone.now()
                bonus.status = 'pending'
                bonus.rejection_reason = ''
                bonus.approved_by = None
                bonus.approved_at = None
                bonus.save(update_fields=[
                    'name', 'reason', 'amount', 'proposed_by', 'proposed_at', 'status',
                    'rejection_reason', 'approved_by', 'approved_at',
                ])
        except ValidationError as exc:
            form.add_error(None, '; '.join(exc.messages))
        else:
            messages.success(request, 'Đã cập nhật và gửi lại đề xuất cho Giám đốc duyệt.')
            return redirect('thuong:detail', bonus.employee_id, bonus.year, bonus.month)

    history = complete_bonus_records(Bonus.objects.select_related('employee__department').filter(
        employee__in=visible_employees(request.user), proposed_by=request.user,
        bonus_type='other')).order_by('-proposed_at', '-pk')
    return render(request, 'bonuses/propose.html', {
        'form': form, 'history': history, 'editing_rejected': True,
    })


@login_required
@require_POST
def delete_proposal(request, bonus_id):
    if not has_role(request.user, HR, MANAGER):
        return access_denied(request)
    bonus = get_object_or_404(complete_bonus_records(Bonus.objects.filter(
        pk=bonus_id, bonus_type='other', status__in=['draft', 'pending', 'rejected'],
        employee__in=visible_employees(request.user))))
    employee_id, year, month = bonus.employee_id, bonus.year, bonus.month
    bonus.delete()
    messages.success(request, 'Đã xóa khoản thưởng chưa được Giám đốc duyệt.')
    return redirect('thuong:detail', employee_id, year, month)


@login_required
@require_POST
def calculate_period(request):
    if not has_role(request.user, HR):
        return access_denied(request)
    form = BonusFilter(request.user, request.POST)
    if not form.is_valid():
        messages.error(request, 'Vui lòng chọn kỳ thưởng hợp lệ trước khi tính tự động.')
        return redirect('thuong:list')
    data = form.cleaned_data
    if not data.get('month') or not data.get('year'):
        messages.error(request, 'Vui lòng chọn tháng và năm trước khi tính thưởng tự động.')
        return redirect('thuong:list')
    employees = form.employee_scope(request.user)
    if data.get('q'):
        employees = employees.filter(Q(full_name__icontains=data['q']) | Q(code__icontains=data['q']))
    created, locked, errors = 0, 0, []
    for employee in employees:
        locked_types = set(Bonus.objects.filter(
            employee=employee, month=data['month'], year=data['year'],
            bonus_type__in=['attendance', 'seniority'], status__in=['pending', 'approved'],
        ).values_list('bonus_type', flat=True))
        if locked_types == {'attendance', 'seniority'}:
            locked += 1
            continue
        automatic, attendance_error = calculate_automatic(employee, data['month'], data['year'])
        saved = False
        with transaction.atomic():
            for bonus_type, name, amount, reason in automatic:
                if bonus_type in locked_types:
                    continue
                Bonus.objects.update_or_create(employee=employee, month=data['month'], year=data['year'],
                    bonus_type=bonus_type, defaults={'name': name, 'amount': amount, 'reason': reason,
                    'proposed_by': request.user, 'proposed_at': timezone.now(), 'status': 'draft',
                    'rejection_reason': ''})
                saved = True
        if saved:
            created += 1
        if attendance_error:
            errors.append(f'{employee.code}: {"; ".join(attendance_error.messages)}')
    if created:
        messages.success(request, f'Đã tính thưởng tự động cho {created} nhân viên; QLNS có thể kiểm tra và gửi duyệt.')
    if locked:
        messages.info(request, f'Bỏ qua {locked} nhân viên đã có thưởng chờ duyệt hoặc đã duyệt.')
    if errors:
        messages.warning(request, 'Chưa tính được: ' + ' | '.join(errors[:5]))
    if not created and not locked and not errors:
        messages.info(request, 'Không có nhân viên trong phạm vi lọc để tính thưởng.')
    return redirect('thuong:list')


@login_required
@require_POST
def submit(request, employee_id, year, month):
    if not has_role(request.user, HR, MANAGER):
        return access_denied(request)
    get_object_or_404(visible_employees(request.user), pk=employee_id)
    count = complete_bonus_records(Bonus.objects.filter(
        employee_id=employee_id, year=year, month=month, status='draft')).update(status='pending')
    if not count:
        messages.error(request, 'Không có đề xuất nháp trong kỳ này để gửi duyệt.')
        return redirect('thuong:list')
    messages.success(request, 'Đã gửi bảng thưởng tổng hợp chờ Giám đốc duyệt.')
    return redirect('thuong:list')


@login_required
@require_POST
def decision(request, employee_id, year, month):
    if not has_role(request.user, DIRECTOR):
        return access_denied(request)
    rows = complete_bonus_records(Bonus.objects.filter(
        employee_id=employee_id, year=year, month=month, status='pending'))
    if not rows.exists():
        raise Http404
    action = request.POST.get('action')
    if action not in ['approve', 'reject']:
        raise ValidationError('Lựa chọn duyệt không hợp lệ.')
    reason = request.POST.get('reason', '').strip()
    if action == 'reject' and not reason:
        messages.error(request, 'Vui lòng nhập lý do từ chối.')
        return redirect('thuong:list')
    rows.update(status='approved' if action == 'approve' else 'rejected', approved_by=request.user,
                approved_at=timezone.now(), rejection_reason=reason if action == 'reject' else '')
    from bang_luong.services.calculations import refresh_employee_payroll
    payroll_error = refresh_employee_payroll(request.user, employee_id, year, month)
    if payroll_error:
        messages.warning(request, 'Chưa đủ điều kiện cập nhật lương: ' + payroll_error)
    messages.success(request, 'Đã cập nhật kết quả duyệt thưởng.')
    return redirect('thuong:list')


@login_required
@require_POST
def export(request):
    if not has_role(request.user, HR, DIRECTOR):
        return access_denied(request)
    form = BonusFilter(request.user, request.POST)
    if not form.is_valid():
        messages.error(request, 'Bộ lọc không hợp lệ.')
        return redirect('thuong:list')
    if not form.cleaned_data.get('month') or not form.cleaned_data.get('year'):
        messages.error(request, 'Vui lòng chọn tháng và năm trước khi xuất bảng thưởng.')
        return redirect('thuong:list')
    form.cleaned_data['status'] = ''
    rows = approved_bonus_records(bonus_rows(request.user, form))
    if not rows.exists():
        messages.error(request, 'Chưa có dữ liệu thưởng đã duyệt để xuất.')
        return redirect('thuong:list')
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
