from datetime import datetime
from decimal import Decimal
from django.core.exceptions import ValidationError
from leaves.models import LeaveDay
from attendance.models import WorkCalendarDay


def calculate_record(record, period):
    record.full_clean()
    calendar = WorkCalendarDay.objects.filter(date=record.date).first()
    if calendar is None:
        raise ValidationError('Chưa cấu hình lịch cho ngày này.')
    record.work_hours = Decimal(0)
    record.actual_units = Decimal(0)
    record.late_minutes = 0
    if record.check_in:
        at = lambda value: datetime.combine(record.date, value)
        start = max(at(record.check_in), at(period.start_time))
        end = min(at(record.check_out), at(period.end_time))
        seconds = max(0, int((end - start).total_seconds()))
        lunch = max(0, int((min(end, at(period.lunch_end)) - max(start, at(period.lunch_start))).total_seconds()))
        if calendar.kind == 'work':
            record.work_hours = Decimal(max(0, seconds - lunch)) / Decimal(3600)
            record.actual_units = min(calendar.expected_units, record.work_hours / period.standard_hours)
            # Phút thực tế, làm tròn lên khi có giây; không tạo khoản phạt tiền.
            late_seconds = max(0, int((at(record.check_in) - at(period.start_time)).total_seconds()))
            record.late_minutes = (late_seconds + 59) // 60
    leave = LeaveDay.objects.filter(employee=record.employee, date=record.date, approved=True).first()
    record.paid_leave_units = leave.units if leave and leave.paid else Decimal(0)
    if leave and record.actual_units + leave.units > calendar.expected_units:
        raise ValidationError('Công thực tế và nghỉ phép vượt công chuẩn ngày; cần kiểm tra dữ liệu.')
    record.paid_units = record.actual_units + record.paid_leave_units
    if record.status == 'leave' and not leave:
        raise ValidationError('Chưa có nghỉ phép được duyệt cho ngày này.')
    for field in ['work_hours', 'actual_units', 'paid_leave_units', 'paid_units']:
        setattr(record, field, getattr(record, field).quantize(Decimal('0.0001')))
    return record
