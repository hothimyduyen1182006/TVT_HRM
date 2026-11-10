"""Lưu, duyệt và mở lại công; dùng chung kiểm tra khóa kỳ và ghi lịch sử."""
import calendar
from datetime import date
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from employees.access import require_role, HR, DIRECTOR
from employees.models import Employee
from attendance.models import AttendancePeriod, AttendanceRecord, AttendanceAuditLog, WorkCalendarDay
from attendance.models import EmployeeAttendanceApproval
from .calculations import calculate_record


def period_is_locked(period, employee_id):
    return bool(period and (period.status == 'approved' or
        period.employee_approvals.filter(employee_id=employee_id).exists()))


def record_is_locked(record):
    period = AttendancePeriod.objects.filter(year=record.date.year, month=record.date.month).first()
    return period_is_locked(period, record.employee_id)


def _recalculate_records(records, period, actor, reason):
    """Tính lại công và ghi lịch sử bằng cùng một luồng khi duyệt kỳ hoặc nhân viên."""
    for record in records:
        before = record_values(record)
        calculate_record(record, period)
        record.save()
        after = record_values(record)
        if before != after:
            AttendanceAuditLog.objects.create(actor=actor, action='recalculate', reason=reason,
                before=before, after=after)


def record_values(record):
    return {field: str(getattr(record, field)) for field in
            ['pk', 'employee_id', 'date', 'check_in', 'check_out', 'status', 'work_hours',
             'late_minutes', 'actual_units', 'paid_leave_units', 'paid_units', 'overtime_hours', 'note']}


@transaction.atomic
def save_record(actor, record, reason):
    require_role(actor, HR, DIRECTOR)
    if not reason.strip():
        raise ValidationError('Cần lý do thay đổi.')
    period = AttendancePeriod.objects.select_for_update().get(year=record.date.year, month=record.date.month)
    if period_is_locked(period, record.employee_id):
        raise ValidationError('Kỳ công đã duyệt, cần mở lại trước.')
    before = {}
    if record.pk:
        old = AttendanceRecord.objects.select_for_update().get(pk=record.pk)
        if old.employee_id != record.employee_id or old.date != record.date:
            raise ValidationError('Không đổi nhân viên/ngày của bản ghi đã tạo.')
        before = record_values(old)
    record.updated_by = actor
    calculate_record(record, period)
    record.full_clean()
    record.save()
    after = record_values(record)
    if not before:
        AttendanceAuditLog.objects.create(actor=actor, action='create_record', reason=reason, before={}, after=after)
    elif before != after:
        AttendanceAuditLog.objects.create(actor=actor, action='edit_record', reason=reason, before=before, after=after)
    return record


@transaction.atomic
def change_period(actor, period_id, action, reason):
    require_role(actor, DIRECTOR)
    period = AttendancePeriod.objects.select_for_update().get(pk=period_id)
    if not reason.strip():
        raise ValidationError('Cần ghi lý do.')
    before = {'period': period.pk, 'status': period.status, 'revision': period.revision}
    if action == 'approve':
        if period.status != 'pending' or not period.policy_confirmed:
            raise ValidationError('Cần xác nhận chính sách và kỳ đang chờ duyệt.')
        days = calendar.monthrange(period.year, period.month)[1]
        configured = WorkCalendarDay.objects.filter(date__year=period.year, date__month=period.month)
        if configured.count() != days:
            raise ValidationError('Phải cấu hình lịch cho tất cả ngày trong tháng.')
        records = AttendanceRecord.objects.filter(date__year=period.year, date__month=period.month)
        employees = Employee.objects.filter(is_active=True, hire_date__lte=date(period.year, period.month, days))
        for employee in employees:
            required = configured.filter(kind='work', date__gte=employee.hire_date).values_list('date', flat=True)
            available = set(records.filter(employee=employee).exclude(status='incomplete').values_list('date', flat=True))
            if not set(required).issubset(available):
                raise ValidationError(f'{employee}: còn ngày làm việc chưa kiểm tra.')
        _recalculate_records(records, period, actor, reason)
        period.status = 'approved'
        period.employee_ids = list(employees.values_list('pk', flat=True))
        for employee in employees:
            EmployeeAttendanceApproval.objects.get_or_create(period=period, employee=employee, defaults={'approved_by': actor})
        period.approved_by = actor
        period.approved_at = timezone.now()
    elif action == 'reopen':
        if period.status != 'approved':
            raise ValidationError('Chỉ mở lại kỳ đã duyệt.')
        from payroll.models import PayrollPeriod
        if PayrollPeriod.objects.filter(attendance_period=period).filter(
                Q(status__in=['approved', 'paid']) | Q(records__status__in=['approved', 'paid'])).exists():
            raise ValidationError('Cần mở lại bảng lương trước; lương đã chi trả không mở lại trực tiếp.')
        period.status = 'pending'
        period.revision += 1
        period.approved_by = None
        period.approved_at = None
        period.employee_approvals.all().delete()
    else:
        raise ValidationError('Thao tác không hợp lệ.')
    period.save()
    AttendanceAuditLog.objects.create(actor=actor, action=action, reason=reason, before=before,
                                      after={'period': period.pk, 'status': period.status, 'revision': period.revision})


@transaction.atomic
def approve_employee(actor, employee, period_id):
    require_role(actor, HR, DIRECTOR)
    period = AttendancePeriod.objects.select_for_update().get(pk=period_id)
    if period_is_locked(period, employee.pk):
        raise ValidationError('Bảng công nhân viên này đã được duyệt.')
    if not period.policy_confirmed:
        raise ValidationError('Chưa xác nhận chính sách kỳ công.')
    days = calendar.monthrange(period.year, period.month)[1]
    schedules = WorkCalendarDay.objects.filter(date__year=period.year, date__month=period.month)
    if schedules.count() != days:
        raise ValidationError('Phải cấu hình lịch đủ tháng trước khi duyệt.')
    records = AttendanceRecord.objects.filter(employee=employee, date__year=period.year, date__month=period.month)
    required = set(schedules.filter(kind='work', date__gte=employee.hire_date).values_list('date', flat=True))
    available = set(records.exclude(status='incomplete').values_list('date', flat=True))
    if not records.exists() or not required.issubset(available) or records.filter(status='incomplete').exists():
        raise ValidationError('Bảng công nhân viên còn thiếu ngày hoặc có dữ liệu chưa kiểm tra.')
    _recalculate_records(records, period, actor, 'Tính lại trước khi duyệt nhân viên')
    approval = EmployeeAttendanceApproval.objects.create(period=period, employee=employee, approved_by=actor)
    AttendanceAuditLog.objects.create(actor=actor, action='approve_employee', reason='Duyệt công nhân viên từ trang chi tiết chấm công',
        before={'approval_status': 'pending'}, after={'employee_id': str(employee.pk),
            'date': f'{period.year:04}-{period.month:02}-01', 'approval_status': 'approved'})
    employee_ids = set(Employee.objects.filter(is_active=True,
        hire_date__lte=date(period.year, period.month, days)).values_list('pk', flat=True))
    if employee_ids and employee_ids.issubset(set(period.employee_approvals.values_list('employee_id', flat=True))):
        period.status = 'approved'
        period.employee_ids = sorted(employee_ids)
        period.approved_by = actor
        period.approved_at = timezone.now()
        period.save()
        AttendanceAuditLog.objects.create(actor=actor, action='approve', reason='Tất cả nhân viên trong kỳ đã được duyệt riêng',
            before={'period': period.pk, 'status': 'pending'}, after={'period': period.pk, 'status': 'approved', 'revision': period.revision})
    return approval
