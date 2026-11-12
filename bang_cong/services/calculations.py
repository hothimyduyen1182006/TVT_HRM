from datetime import datetime, time
from decimal import Decimal, ROUND_DOWN
from django.core.exceptions import ValidationError
from nghi_phep.models import LeaveDay
from bang_cong.models import WorkCalendarDay, AttendancePeriod, AttendanceRecord

OT_POLICY = 'automatic-checkout-1700-v1'
ZERO = Decimal(0)


def interval_hours(day, start, end):
    seconds = max(0, int((datetime.combine(day, end) - datetime.combine(day, start)).total_seconds()))
    return (Decimal(seconds) / Decimal(3600)).quantize(Decimal('0.0001'), rounding=ROUND_DOWN)


def automatic_overtime(record, period=None, day=None):
    """Pure calculation for every department; historical approval rows are never sources."""
    result = {'id': record.pk, 'date': str(record.date), 'start': '', 'end': '',
              'hours': ZERO, 'multiplier': ZERO, 'warnings': [], 'error': ''}
    if (record.status != 'present' or not record.check_in or not record.check_out
            or record.check_out <= record.check_in or record.date < record.employee.hire_date):
        return result
    period = period or AttendancePeriod.objects.filter(year=record.date.year, month=record.date.month).first()
    day = day or WorkCalendarDay.objects.filter(date=record.date).first()
    if not period or not day:
        result['error'] = 'Thiếu cấu hình kỳ công hoặc lịch ngày để xác định OT.'
        return result
    start = max(record.check_in, time(17)) if day.kind == 'work' else record.check_in
    end = record.check_out
    if start >= end:
        return result
    hours = interval_hours(record.date, start, end)
    if day.kind != 'work':
        lunch_start, lunch_end = max(start, period.lunch_start), min(end, period.lunch_end)
        if lunch_start < lunch_end:
            hours -= interval_hours(record.date, lunch_start, lunch_end)
    result.update(start=str(start), end=str(end), hours=max(ZERO, hours),
                  multiplier={'work': Decimal('1.5'), 'rest': Decimal(2), 'holiday': Decimal(3)}[day.kind])
    if hours and (start < time(6) or end > time(22)):
        result['error'] = 'Có giờ ban đêm (22:00–06:00); chưa hỗ trợ công thức OT ban đêm. Cần đối soát trước khi tính lương.'
    normal = min(period.standard_hours * day.expected_units, period.standard_hours)
    if (day.kind == 'work' and hours > normal / 2) or hours + record.work_hours > 12:
        result['warnings'].append('Vượt giới hạn giờ làm thêm trong ngày; giữ nguyên giờ thực tế, cần kiểm tra tổ chức lao động.')
    return result


def payroll_overtime(employee, year, month):
    period = AttendancePeriod.objects.filter(year=year, month=month).first()
    days = {day.date: day for day in WorkCalendarDay.objects.filter(date__year=year, date__month=month)}
    rows = []
    for record in AttendanceRecord.objects.filter(employee=employee, date__year=year, date__month=month).select_related('employee').order_by('date'):
        item = automatic_overtime(record, period, days.get(record.date))
        if item['error']:
            raise ValidationError(f"{record.date}: {item['error']}")
        if item['hours']:
            rows.append(item)
    monthly = sum((item['hours'] for item in rows), ZERO)
    annual = ZERO
    periods = {(p.year, p.month): p for p in AttendancePeriod.objects.filter(year=year)}
    year_days = {d.date: d for d in WorkCalendarDay.objects.filter(date__year=year)}
    for record in AttendanceRecord.objects.filter(employee=employee, date__year=year).select_related('employee'):
        annual += automatic_overtime(record, periods.get((year, record.date.month)), year_days.get(record.date))['hours']
    if rows and monthly > 40:
        rows[0]['warnings'].append('Vượt 40 giờ OT/tháng; không tự cắt giờ hoặc tiền đã làm.')
    if rows and annual > 200:
        rows[0]['warnings'].append('Vượt ngưỡng mặc định 200 giờ OT/năm; cần kiểm tra điều kiện ngoại lệ theo pháp luật.')
    return rows


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
        end = min(at(record.check_out), at(period.end_time), at(time(17)))
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
