from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone
from attendance.models import AttendancePeriod
from employees.access import require_role, DIRECTOR
from payroll.models import PayrollPeriod, PayrollAuditLog, PayrollRecord
from .calculations import snapshot, payroll_values
from .source_data import legacy_breakdown
from .tax import tax_source_error
from decimal import Decimal, InvalidOperation
from bonuses.models import Bonus, payroll_bonus_records


def bonus_source_error(record):
    """Check saved bonus sources without recalculating or modifying a locked payslip."""
    attendance = record.period.attendance_period
    try:
        rows = payroll_bonus_records(Bonus.objects.filter(employee_id=record.employee_id,
            year=attendance.year, month=attendance.month))
        current = {row.pk: row.amount for row in rows}
        saved = {int(item['id']): Decimal(str(item['amount']))
                 for item in record.breakdown.get('bonuses', [])}
    except ValidationError as error:
        return '; '.join(error.messages)
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return 'Phiếu lương thiếu thông tin thưởng nguồn để đối chiếu. Cần kiểm tra lại trước khi chi trả.'
    if current != saved or sum(current.values(), Decimal(0)) != record.bonus_pay:
        return 'Bảng thưởng đã thay đổi so với phiếu lương đã lưu. Cần mở lại và tính lại lương trước khi chi trả.'
    return ''


def overtime_source_error(record):
    from attendance.services.calculations import payroll_overtime, OT_POLICY
    attendance = record.period.attendance_period
    try:
        rows = payroll_overtime(record.employee, attendance.year, attendance.month)
        if (rows or record.ot_hours or record.ot_pay) and record.breakdown.get('source_data', {}).get('overtime_policy') != OT_POLICY:
            return 'Nguồn OT thuộc cơ chế cũ. Cần mở lại và tính lại lương; giữ nguyên phiếu đã chi trả.'
        current = {row['id']: (row['date'], row['start'], row['end'], row['hours'], row['multiplier']) for row in rows}
        saved = {int(item['id']): (item['date'], item['start'], item['end'], Decimal(item['hours']), Decimal(item['multiplier'])) for item in record.breakdown.get('ot', [])}
        rate = Decimal(str(record.breakdown.get('overtime_hourly_rate', 0)))
        if rows:
            from payroll.models import PayrollInput
            inputs = PayrollInput.objects.filter(employee=record.employee, period=record.period, verified=True).first()
            if (not inputs or not inputs.overtime_hourly_rate or not inputs.overtime_basis.strip()
                    or rate != inputs.overtime_hourly_rate
                    or record.breakdown.get('overtime_basis') != inputs.overtime_basis):
                return 'Căn cứ lương giờ OT đã thay đổi hoặc còn thiếu. Cần mở lại và tính lại lương.'
        expected_amount = sum((row['hours'] * row['multiplier'] * rate for row in rows), Decimal(0))
        saved_amount = sum((Decimal(item['amount']) for item in record.breakdown.get('ot', [])), Decimal(0))
        if current != saved or sum((row['hours'] for row in rows), Decimal(0)) != record.ot_hours or expected_amount.quantize(Decimal('0.00000001')) != record.ot_pay or saved_amount != expected_amount:
            return 'Nguồn OT đã thay đổi. Cần mở lại và tính lại lương trước khi duyệt hoặc chi trả.'
    except ValidationError as error:
        return '; '.join(error.messages)
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return 'Thiếu nguồn OT để đối chiếu. Cần mở lại và tính lại lương.'
    return ''


def record_approval_error(record, period=None, attendance=None):
    error = overtime_source_error(record)
    if error:
        return error
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
            if connection.vendor == 'sqlite':
                # Compare the same representation Django reads from SQLite's REAL storage.
                # The calculation and saved amounts are unchanged; avoid false stale-source errors.
                expression = definition.get_col(record._meta.db_table)
                prepared = definition.get_db_prep_save(expected, connection)
                converter = connection.ops.get_decimalfield_converter(expression)
                expected = converter(float(prepared), expression, connection)
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
        return 'Dữ liệu nguồn đã thay đổi và lương chưa cập nhật được. Cần kiểm tra căn cứ tính lương trước khi duyệt.'
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
        for record in period.records.all():
            error = overtime_source_error(record) or tax_source_error(record)
            if error:
                raise ValidationError(f'{record.employee_code}: {error}')
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
        for record in period.records.all():
            error = bonus_source_error(record) or overtime_source_error(record) or tax_source_error(record)
            if error:
                raise ValidationError(f'{record.employee_code}: {error}')
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
    if action == 'reopen':
        from .calculations import refresh_employee_payroll
        for employee_id in period.records.filter(status='pending').values_list('employee_id', flat=True):
            refresh_employee_payroll(actor, employee_id, attendance.year, attendance.month)


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
