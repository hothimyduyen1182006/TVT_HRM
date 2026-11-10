from datetime import timedelta
import mimetypes
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import SuspiciousFileOperation, ValidationError
from django.db import transaction, IntegrityError
from django.db.models import Q, Count
from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse, Http404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe
from employees.access import visible_employees, has_role, require_role, HR, DIRECTOR, MANAGER
from employees.models import Employee, Department
from .forms import LeaveRequestForm, LeaveFilterForm
from .models import LeaveDay, LeaveRequest


def reviewer_scope(user):
    if has_role(user, HR, DIRECTOR, MANAGER):
        return visible_employees(user)
    return Employee.objects.none()


@login_required
def leave_list(request):
    own = Employee.objects.filter(user=request.user, is_active=True).first()
    scope = reviewer_scope(request.user)
    is_reviewer = has_role(request.user, HR, DIRECTOR, MANAGER)
    base = LeaveRequest.objects.select_related('employee', 'employee__department', 'reviewed_by')
    if is_reviewer:
        base = base.filter(employee__in=scope)
    elif own:
        base = base.filter(employee=own)
    else:
        base = base.none()

    form = LeaveRequestForm(request.POST or None, request.FILES or None)
    if request.method == 'POST':
        if not own:
            messages.error(request, 'Tài khoản chưa được liên kết với hồ sơ nhân viên.')
        elif form.is_valid():
            item = form.save(commit=False)
            item.employee = own
            item.paid = item.leave_type in ('annual', 'sick')
            try:
                item.full_clean()
                item.save()
            except ValidationError as exc:
                for error in exc.messages:
                    form.add_error(None, error)
            else:
                messages.success(request, 'Đã gửi đơn nghỉ phép. Bạn có thể theo dõi trạng thái trong lịch sử đơn.')
                return redirect('leaves:list')
    departments = Department.objects.filter(employee__in=scope).distinct() if is_reviewer else Department.objects.none()
    filters = LeaveFilterForm(departments, request.GET)
    rows = base
    if filters.is_valid():
        data = filters.cleaned_data
        if data['q']:
            rows = rows.filter(Q(employee__full_name__icontains=data['q']) |
                               Q(employee__code__icontains=data['q']))
        if data['department']:
            rows = rows.filter(employee__department_id=data['department'])
        if data['status']:
            rows = rows.filter(status=data['status'])
        if data['leave_type']:
            rows = rows.filter(leave_type=data['leave_type'])
        if data['start_date']:
            rows = rows.filter(end_date__gte=data['start_date'])
        if data['end_date']:
            rows = rows.filter(start_date__lte=data['end_date'])
    counts = base.aggregate(total=Count('id'), pending=Count('id', filter=Q(status='pending')),
                            approved=Count('id', filter=Q(status='approved')),
                            rejected=Count('id', filter=Q(status='rejected')))
    return render(request, 'leaves/list.html', {
        'requests': rows, 'form': form, 'filters': filters, 'is_reviewer': is_reviewer,
        'own_employee': own, 'can_review': is_reviewer, 'counts': counts,
    })


@login_required
def leave_detail(request, pk):
    scope = visible_employees(request.user)
    item = get_object_or_404(LeaveRequest.objects.select_related(
        'employee', 'employee__department', 'reviewed_by'), pk=pk, employee__in=scope)
    can_review = has_role(request.user, HR, DIRECTOR, MANAGER)
    return render(request, 'leaves/detail.html', {'item': item, 'can_review': can_review,
                  'days_count': (item.end_date - item.start_date).days + 1})


@never_cache
@login_required
@require_safe
def leave_evidence(request, pk):
    item = get_object_or_404(LeaveRequest, pk=pk, employee__in=visible_employees(request.user))
    if not item.evidence:
        raise Http404
    content_type = mimetypes.guess_type(item.evidence.name)[0] or 'application/octet-stream'
    inline_image = content_type in ('image/jpeg', 'image/png', 'image/webp', 'image/gif')
    try:
        opened = item.evidence.open('rb')
    except (OSError, SuspiciousFileOperation):
        raise Http404
    response = FileResponse(opened, content_type=content_type, as_attachment=not inline_image,
                            filename=item.evidence.name.rsplit('/', 1)[-1])
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@login_required
@require_POST
def review_leave(request, pk, action):
    require_role(request.user, HR, DIRECTOR, MANAGER)
    item = get_object_or_404(LeaveRequest, pk=pk, employee__in=visible_employees(request.user))
    if item.status != 'pending' or action not in ('approve', 'reject'):
        messages.error(request, 'Đơn này đã được xử lý hoặc thao tác không hợp lệ.')
        return redirect('leaves:detail', pk=item.pk)
    review_note = request.POST.get('review_note', '').strip()
    if action == 'reject' and not review_note:
        messages.error(request, 'Vui lòng nhập lý do từ chối để nhân viên biết nội dung xử lý.')
        return redirect('leaves:detail', pk=item.pk)
    try:
        with transaction.atomic():
            item = LeaveRequest.objects.select_for_update().get(pk=pk)
            if item.status != 'pending':
                raise ValidationError('Đơn này đã được xử lý.')
            if action == 'approve':
                day = item.start_date
                while day <= item.end_date:
                    leave = LeaveDay(employee=item.employee, date=day, units=item.units,
                                     paid=item.paid, reason=item.reason, approved=True)
                    leave.full_clean()
                    leave.save()
                    day += timedelta(days=1)
                item.status = 'approved'
                item.review_note = review_note
            else:
                item.status = 'rejected'
                item.review_note = review_note
            item.reviewed_by = request.user
            item.reviewed_at = timezone.now()
            item.save(update_fields=['status', 'review_note', 'reviewed_by', 'reviewed_at'])
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
    except IntegrityError:
        messages.error(request, 'Một ngày trong đơn đã có dữ liệu nghỉ phép. Vui lòng kiểm tra bảng công.')
    else:
        messages.success(request, 'Đã cập nhật trạng thái đơn nghỉ phép.')
    return redirect('leaves:detail', pk=item.pk)
