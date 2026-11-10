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
    if record.check_in and record.check_out:
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


def available_overtime(record, period, day):
    if not record or record.status != 'present' or not record.check_in or not record.check_out:
        return Decimal(0)
    at = lambda value: datetime.combine(record.date, value)
    start, end = at(record.check_in), at(record.check_out)
    if end <= start:
        return Decimal(0)
    if day.kind == 'work':
        seconds = max(0, int((min(end, at(period.start_time)) - start).total_seconds()))
        seconds += max(0, int((end - max(start, at(period.end_time))).total_seconds()))
    else:
        seconds = int((end - start).total_seconds())
        seconds -= max(0, int((min(end, at(period.lunch_end)) - max(start, at(period.lunch_start))).total_seconds()))
    return Decimal(seconds) / Decimal(3600)


def validate_overtime(overtime, record=None, period=None):
    if not overtime.approved:
        return
    if overtime.status not in ['approved', 'legacy']:
        raise ValidationError('Chỉ OT đã duyệt mới được tính lương.')
    from attendance.models import AttendanceRecord, AttendancePeriod, WorkCalendarDay
    if not overtime.employee_id or not overtime.date or overtime.hours is None:
        raise ValidationError('OT cần có nhân viên, ngày và số giờ.')
    period = period or AttendancePeriod.objects.filter(year=overtime.date.year, month=overtime.date.month).first()
    day = WorkCalendarDay.objects.filter(date=overtime.date).first()
    record = record or AttendanceRecord.objects.filter(employee_id=overtime.employee_id, date=overtime.date).first()
    if not period or not day:
        raise ValidationError('Chưa có kỳ công hoặc lịch làm việc để đối chiếu OT.')
    if not record or record.status != 'present' or not record.check_in or not record.check_out:
        raise ValidationError('Chỉ duyệt OT khi có chấm công đủ giờ vào / ra và trạng thái Có mặt.')
    maximum = available_overtime(record, period, day)
    if overtime.hours > maximum:
        raise ValidationError(f'OT {overtime.hours} giờ vượt thời gian ngoài ca thực tế ({maximum:.2f} giờ).')


def validated_overtime(rows):
    rows = list(rows)
    for row in rows:
        row.full_clean()
    return rows
