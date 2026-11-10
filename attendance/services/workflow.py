"""Lưu, duyệt và mở lại công; dùng chung kiểm tra khóa kỳ và ghi lịch sử."""
import calendar
from datetime import date
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from employees.access import require_role, HR, DIRECTOR, MANAGER
from employees.models import Employee
from attendance.models import AttendancePeriod, AttendanceRecord, AttendanceAuditLog, WorkCalendarDay
from attendance.models import EmployeeAttendanceApproval
from .calculations import calculate_record, interval_hours, overtime_multiplier
from decimal import Decimal


def can_approve_overtime(user, employee):
    return bool(user.is_authenticated and user.is_active and employee.user_id != user.pk
        and user.groups.filter(name=MANAGER).exists()
        and Employee.objects.filter(pk=employee.pk,is_active=True,department__allows_overtime=True,
                                    department__manager__user=user).exists())


@transaction.atomic
def submit_overtime(actor, record_id, start, end, reason):
    from attendance.models import OvertimeApproval
    link=AttendanceRecord.objects.get(pk=record_id)
    employee=Employee.objects.select_for_update().select_related('department').get(pk=link.employee_id)
    if employee.user_id != actor.pk or not actor.is_active or not employee.is_active or not employee.department.allows_overtime:
        raise PermissionDenied('Chỉ nhân viên Phòng Sản xuất được gửi yêu cầu của bản thân.')
    period=AttendancePeriod.objects.select_for_update().get(year=link.date.year,month=link.date.month)
    record=AttendanceRecord.objects.select_for_update().get(pk=record_id)
    if not period.policy_confirmed:
        raise ValidationError('Chưa xác nhận cấu hình ca làm việc.')
    if not reason.strip() or len(reason.strip())>2000:
        raise ValidationError('Cần lý do tăng ca, tối đa 2000 ký tự.')
    day=WorkCalendarDay.objects.get(date=record.date)
    hours=interval_hours(record.date,start,end)
    row=OvertimeApproval(employee=employee,department=employee.department,date=record.date,
        start_time=start,end_time=end,requested_hours=hours,hours=hours,multiplier=overtime_multiplier(day),
        status='pending',approved=False,request_reason=reason.strip(),requested_by=actor,requested_at=timezone.now())
    row.save()
    _log_overtime(row,actor,'submit_ot',reason.strip(),'','pending')
    return row


@transaction.atomic
def approve_overtime(actor, overtime_id, hours):
    return _review_overtime(actor,overtime_id,'approved',hours=hours)


@transaction.atomic
def reject_overtime(actor, overtime_id, reason):
    return _review_overtime(actor,overtime_id,'rejected',reason=reason)


def _review_overtime(actor, overtime_id, status, hours=None, reason=''):
    from attendance.models import OvertimeApproval
    link=OvertimeApproval.objects.get(pk=overtime_id)
    employee=Employee.objects.select_for_update().select_related('department').get(pk=link.employee_id)
    if not can_approve_overtime(actor,employee) or link.department_id != employee.department_id:
        raise PermissionDenied('Chỉ Trưởng phòng Sản xuất phụ trách được xử lý, không tự duyệt hoặc duyệt khác phòng.')
    AttendancePeriod.objects.select_for_update().get(year=link.date.year,month=link.date.month)
    row=OvertimeApproval.objects.select_for_update().get(pk=overtime_id)
    if row.status != 'pending' or row.approved:
        raise ValidationError('Chỉ xử lý yêu cầu đang Chờ duyệt; không được duyệt lại.')
    if status=='rejected' and (not reason.strip() or len(reason.strip())>2000):
        raise ValidationError('Cần lý do từ chối, tối đa 2000 ký tự.')
    row.status=status
    row.reviewed_by,row.reviewed_at=actor,timezone.now()
    row.approved=(status=='approved')
    if row.approved:
        row.hours=hours
        row.approved_by,row.approved_at=actor,row.reviewed_at
    else:
        row.rejection_reason=reason.strip()
        row.approved_by=row.approved_at=None
    row.save()
    _log_overtime(row,actor,'approve_ot' if row.approved else 'reject_ot',reason.strip() or 'Duyệt OT','pending',status)
    return row


def _log_overtime(row, actor, action, reason, before, after):
    AttendanceAuditLog.objects.create(actor=actor,action=action,reason=reason,before={'status':before},
        after={'status':after,'ot_id':str(row.pk),'employee_id':str(row.employee_id),'date':str(row.date),
               'start':str(row.start_time),'end':str(row.end_time),'hours':str(row.hours)})


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
             'late_minutes', 'actual_units', 'paid_leave_units', 'paid_units', 'note']}


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
    from attendance.models import OvertimeApproval
    from .calculations import validate_overtime
    for overtime in OvertimeApproval.objects.filter(employee=record.employee,date=record.date,status='approved'):
        validate_overtime(overtime,record=record,period=period)
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
        from attendance.models import OvertimeApproval
        if OvertimeApproval.objects.filter(date__year=period.year,date__month=period.month,status='pending').exists():
            raise ValidationError('Còn OT chờ duyệt; Trưởng phòng cần xử lý trước khi khóa kỳ công.')
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
    from attendance.models import OvertimeApproval
    if OvertimeApproval.objects.filter(employee=employee,date__year=period.year,date__month=period.month,status='pending').exists():
        raise ValidationError('Còn OT chờ duyệt; Trưởng phòng cần xử lý trước khi duyệt công.')
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
