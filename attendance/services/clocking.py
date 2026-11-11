from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from employees.models import Employee
from attendance.models import AttendancePeriod, AttendanceRecord, WorkCalendarDay
from .calculations import calculate_record
from .workflow import period_is_locked


@transaction.atomic
def punch(actor, action, note=''):
    now = timezone.localtime().replace(microsecond=0)
    today = now.date()
    employee = Employee.objects.select_for_update().filter(user=actor, is_active=True).first()
    if not employee:
        raise PermissionDenied('Tài khoản chưa liên kết nhân viên đang làm việc.')
    period = AttendancePeriod.objects.select_for_update().filter(year=today.year, month=today.month).first()
    if not period or not period.policy_confirmed:
        raise ValidationError('Nhân sự cần cấu hình và xác nhận kỳ công hiện tại trước.')
    if period_is_locked(period, employee.pk, today):
        raise ValidationError('Bảng công đã duyệt, không thể chấm công thêm.')
    day = WorkCalendarDay.objects.filter(date=today).first()
    if not day or day.kind != 'work':
        raise ValidationError('Hôm nay chưa có lịch làm việc thông thường được cấu hình.')
    if today < employee.hire_date:
        raise ValidationError('Chưa đến ngày vào làm.')
    record = AttendanceRecord.objects.select_for_update().filter(employee=employee, date=today).first()
    if action == 'in':
        if record:
            raise ValidationError('Hôm nay đã có bản ghi chấm công. Không thể check-in lại.')
        record = AttendanceRecord(employee=employee, date=today, check_in=now.time(), status='incomplete')
    elif action == 'out':
        if not record or not record.check_in:
            raise ValidationError('Bạn cần check-in trước.')
        if record.check_out or record.status != 'incomplete':
            raise ValidationError('Bản ghi đã kết thúc hoặc cần nhân sự kiểm tra.')
        if now.time() <= record.check_in:
            raise ValidationError('Giờ check-out phải sau giờ check-in.')
        if len(note) > 2000:
            raise ValidationError('Ghi chú tối đa 2000 ký tự.')
        record.check_out = now.time()
        record.status = 'present'
        record.note = note.strip()
        calculate_record(record, period)
    else:
        raise ValidationError('Thao tác không hợp lệ.')
    record.updated_by = actor
    record.full_clean()
    record.save()
    return record
