from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from attendance.models import AttendancePeriod
from employees.access import require_role, DIRECTOR
from payroll.models import PayrollPeriod, PayrollAuditLog, PayrollRecord
from .calculations import snapshot, payroll_values
from .source_data import legacy_breakdown
from decimal import Decimal, InvalidOperation


def record_approval_error(record, period=None, attendance=None):
    period = period or record.period
    attendance = attendance or period.attendance_period
    approval = attendance.employee_approvals.filter(employee_id=record.employee_id).first()
    if not approval and attendance.status != 'approved':
        return 'Bảng công của nhân viên này chưa được duyệt.'
    try:
        current = payroll_values(record.employee, attendance, period)
    except ValidationError as exc:
        return '; '.join(exc.messages)
    changed = False
    for field in ['base_salary', 'standard_units', 'paid_units', 'leave_units', 'late_minutes', 'ot_hours',
                  'attendance_pay', 'ot_pay', 'bonus_pay', 'allowance', 'insurance', 'tax', 'deductions', 'net_pay']:
        expected = current[field]
        definition = PayrollRecord._meta.get_field(field)
        if isinstance(expected, Decimal) and hasattr(definition, 'decimal_places'):
            expected = expected.quantize(Decimal(1).scaleb(-definition.decimal_places))
        if getattr(record, field) != expected:
            changed = True
            break
    if not changed:
        if 'source_data' in record.breakdown:
            changed = record.breakdown['source_data'] != current['breakdown']['source_data']
        else:
            try:
                changed = legacy_breakdown(record.breakdown) != legacy_breakdown(current['breakdown'])
            except (KeyError, TypeError, ValueError, InvalidOperation):
                return 'Phiếu cũ thiếu dữ liệu đối chiếu. Hãy tính lại lương trước khi duyệt.'
    if changed:
        return 'Dữ liệu dùng tính lương đã thay đổi so với phiếu đã lưu. Hãy bấm Tính lương trước khi duyệt.'
    return ''


@transaction.atomic
def change_payroll(actor, period_id, action, reason, evidence=''):
    require_role(actor, DIRECTOR)
    if not reason.strip():
        raise ValidationError('Cần ghi lý do.')
    link = PayrollPeriod.objects.get(pk=period_id)
    attendance = AttendancePeriod.objects.select_for_update().get(pk=link.attendance_period_id)
    period = PayrollPeriod.objects.select_for_update().get(pk=period_id)
    if action == 'approve':
        if period.status != 'pending' or not period.records.exists():
            raise ValidationError('Cần kỳ chờ duyệt có kết quả tính lương.')
        if attendance.status != 'approved':
            raise ValidationError('Bảng công chưa được duyệt.')
        for record in period.records.filter(status='pending'):
            error = record_approval_error(record, period, attendance)
            if error:
                raise ValidationError(f'{record.employee_code}: {error}')
        period.status = 'approved'
        period.approved_by = actor
        period.approved_at = timezone.now()
        period.records.filter(status='pending').update(status='approved', approved_by=actor, approved_at=period.approved_at)
    elif action == 'paid':
        if period.status != 'approved' or not evidence.strip() or period.records.filter(status='pending').exists():
            raise ValidationError('Chỉ xác nhận kỳ đã duyệt khi có bằng chứng thanh toán.')
        period.status = 'paid'
        period.paid_by = actor
        period.paid_at = timezone.now()
        period.payment_evidence = evidence
        period.records.all().update(status='paid')
    elif action == 'reopen':
        if period.status == 'paid' or not (period.status == 'approved' or period.records.filter(status='approved').exists()):
            raise ValidationError('Chỉ mở lại kỳ đã duyệt và chưa chi trả.')
        period.status = 'pending'
        period.approved_by = None
        period.approved_at = None
        period.attendance_revision = 0  # Bắt buộc tính lại trước khi duyệt.
        period.records.all().update(status='pending', approved_by=None, approved_at=None)
    else:
        raise ValidationError('Thao tác không hợp lệ.')
    period.save()
    PayrollAuditLog.objects.create(period=period, actor=actor, action=action, reason=reason, snapshot=snapshot(period))


@transaction.atomic
def approve_record(actor, record_id):
    require_role(actor, DIRECTOR)
    link = PayrollRecord.objects.select_related('period').get(pk=record_id)
    attendance = AttendancePeriod.objects.select_for_update().get(pk=link.period.attendance_period_id)
    period = PayrollPeriod.objects.select_for_update().get(pk=link.period_id)
    record = PayrollRecord.objects.select_for_update().get(pk=record_id)
    if record.status != 'pending' or period.status != 'pending':
        raise ValidationError('Phiếu lương này đã duyệt hoặc đã chi trả.')
    error = record_approval_error(record, period, attendance)
    if error:
        raise ValidationError(error)
    record.status = 'approved'
    record.approved_by = actor
    record.approved_at = timezone.now()
    record.save(update_fields=['status', 'approved_by', 'approved_at'])
    expected_ids = set(attendance.employee_ids)
    approved_ids = set(period.records.filter(status__in=['approved', 'paid']).values_list('employee_id', flat=True))
    if (attendance.status == 'approved' and expected_ids and expected_ids.issubset(approved_ids)
            and not period.records.filter(status='pending').exists()):
        period.status = 'approved'
        period.approved_by = actor
        period.approved_at = record.approved_at
        period.save()
    PayrollAuditLog.objects.create(period=period, actor=actor, action='approve_employee',
        reason=f'Duyệt phiếu lương riêng của {record.employee_code}',
        snapshot=[{key: str(value) for key, value in PayrollRecord.objects.filter(pk=record.pk).values().get().items()}])
    return record
