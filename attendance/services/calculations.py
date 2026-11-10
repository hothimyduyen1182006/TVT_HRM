from datetime import datetime, time
from decimal import Decimal, ROUND_DOWN
from django.core.exceptions import ValidationError
from leaves.models import LeaveDay
from attendance.models import WorkCalendarDay
from django.db.models import Sum, Q, F, Case, When, DecimalField


def overtime_window(record, period):
    """OT ban ngày cùng ngày; check-out muộn chỉ cung cấp căn cứ, không tạo yêu cầu."""
    if not record or record.status != 'present' or not record.check_in or not record.check_out or not period:
        return None
    day = WorkCalendarDay.objects.filter(date=record.date).first()
    if not day:
        return None
    start = max(record.check_in, period.end_time if day.kind == 'work' else time(6), time(6))
    end = min(record.check_out, time(22))
    return (start, end) if start < end else None


def interval_hours(day, start, end):
    seconds = int((datetime.combine(day,end)-datetime.combine(day,start)).total_seconds())
    return (Decimal(seconds)/Decimal(3600)).quantize(Decimal('0.01'),rounding=ROUND_DOWN)


def overtime_candidate(record, period):
    from attendance.models import OvertimeApproval
    window=overtime_window(record,period)
    if not window:
        return None
    start,end=window
    if OvertimeApproval.objects.filter(employee_id=record.employee_id,date=record.date,status='legacy',approved=True).exists():
        return None
    day=WorkCalendarDay.objects.get(date=record.date)
    if day.kind!='work' and start<period.lunch_end and end>period.lunch_start:
        if start<period.lunch_start:
            end=period.lunch_start
        else:
            start=period.lunch_end
    for row in OvertimeApproval.objects.filter(employee_id=record.employee_id,date=record.date).exclude(
            start_time__isnull=True).order_by('start_time'):
        if row.end_time<=start or row.start_time>=end:
            continue
        if row.start_time>start:
            return start,row.start_time
        start=max(start,row.end_time)
    return (start,end) if start<end and interval_hours(record.date,start,end)>=Decimal('0.01') else None


def overtime_multiplier(day):
    return {'work':Decimal('1.5'),'rest':Decimal(2),'holiday':Decimal(3)}[day.kind]


def validate_overtime(overtime, record=None, period=None):
    from attendance.models import AttendanceRecord, AttendancePeriod, OvertimeApproval
    from employees.models import Employee
    if overtime.status == 'legacy':
        return  # Dữ liệu cũ chỉ đọc, không đủ điều kiện vào nguồn lương OT mới.
    if overtime.status == 'rejected':
        return
    if not overtime.department_id:
        raise ValidationError('Thiếu phòng ban tại thời điểm gửi OT.')
    if not overtime.start_time or not overtime.end_time or not overtime.date:
        raise ValidationError('Cần ngày và khoảng giờ OT.')
    start,end=overtime.start_time,overtime.end_time
    if start >= end:
        raise ValidationError('Giờ bắt đầu phải nhỏ hơn giờ kết thúc. Chưa hỗ trợ OT qua ngày.')
    if start < time(6) or end > time(22):
        raise ValidationError('Chưa hỗ trợ OT ban đêm (22:00–06:00); cần quy trình tính riêng.')
    employee=Employee.objects.select_related('department').get(pk=overtime.employee_id)
    if overtime.status == 'pending' and (not employee.is_active or not employee.department.allows_overtime
            or overtime.department_id != employee.department_id):
        raise ValidationError('Chỉ nhân viên Phòng Sản xuất hiện tại được gửi OT.')
    period=period or AttendancePeriod.objects.filter(year=overtime.date.year,month=overtime.date.month).first()
    day=WorkCalendarDay.objects.filter(date=overtime.date).first()
    record=record or AttendanceRecord.objects.filter(employee_id=employee.pk,date=overtime.date).first()
    window=overtime_window(record,period)
    if not window or start < window[0] or end > window[1]:
        raise ValidationError('Khoảng OT phải nằm trong thời gian ngoài ca có đủ check-in/check-out thực tế.')
    if day.kind != 'work' and start < period.lunch_end and end > period.lunch_start:
        raise ValidationError('Khoảng OT trùng nghỉ trưa. Hãy tách yêu cầu trước và sau giờ nghỉ.')
    expected=interval_hours(overtime.date,start,end)
    if overtime.requested_hours != expected or expected < Decimal('0.01'):
        raise ValidationError('Số giờ đề nghị phải khớp khoảng OT, tính theo thời gian thực tế.')
    if not overtime.hours or overtime.hours <= 0 or overtime.hours > expected:
        raise ValidationError('Số giờ được duyệt không được vượt số giờ thực tế đã đề nghị.')
    if overtime.status == 'rejected':
        return
    if overtime.multiplier != overtime_multiplier(day):
        raise ValidationError('Hệ số OT phải khớp lịch: ngày thường 1,5; nghỉ tuần 2; lễ 3.')
    others=OvertimeApproval.objects.filter(employee_id=employee.pk).exclude(pk=overtime.pk)
    active=others.filter(status__in=['pending','approved'])
    if active.filter(date=overtime.date,start_time__lt=end,end_time__gt=start).exists():
        raise ValidationError('Khoảng OT trùng hoặc chồng lấn với yêu cầu đã gửi/đã duyệt.')
    if others.filter(date=overtime.date,status='legacy',approved=True).exists():
        raise ValidationError('Ngày này có OT lịch sử chưa có khoảng giờ; HR cần đối soát riêng.')
    effective=Case(When(status='pending',then=F('requested_hours')),default=F('hours'),output_field=DecimalField())
    reserved=others.filter(Q(status__in=['pending','approved'])|Q(status='legacy',approved=True))
    def total(rows):
        return rows.aggregate(value=Sum(effective))['value'] or Decimal(0)
    hours=overtime.hours if overtime.status == 'approved' else expected
    normal=period.standard_hours*day.expected_units
    daily_limit=min(normal/2,Decimal(12)-record.work_hours) if day.kind=='work' else Decimal(12)
    if total(reserved.filter(date=overtime.date))+hours > daily_limit:
        raise ValidationError('Vượt giới hạn OT ngày: tối đa 50% giờ bình thường và tổng giờ làm không quá 12 giờ.')
    if total(reserved.filter(date__year=overtime.date.year,date__month=overtime.date.month))+hours > 40:
        raise ValidationError('Vượt giới hạn 40 giờ OT/tháng (gồm yêu cầu đang chờ).')
    if total(reserved.filter(date__year=overtime.date.year))+hours > 200:
        raise ValidationError('Vượt giới hạn 200 giờ OT/năm (gồm yêu cầu đang chờ).')


def payroll_overtime(employee, year, month):
    from attendance.models import OvertimeApproval
    rows=OvertimeApproval.objects.filter(employee=employee,date__year=year,date__month=month,status='approved')
    for row in rows:
        row.full_clean()
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
