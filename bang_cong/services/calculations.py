from datetime import datetime, time
from decimal import Decimal, ROUND_DOWN
from django.core.exceptions import ValidationError
from nghi_phep.models import LeaveDay
from bang_cong.models import LichLamViec, KyCong, ChamCong

OT_POLICY = 'automatic-checkout-1700-v1'
ZERO = Decimal(0)


def interval_hours(day, start, end):
    seconds = max(0, int((datetime.combine(day, end) - datetime.combine(day, start)).total_seconds()))
    return (Decimal(seconds) / Decimal(3600)).quantize(Decimal('0.0001'), rounding=ROUND_DOWN)


def automatic_overtime(record, period=None, day=None):
    """Pure calculation for every department; historical approval rows are never sources."""
    result = {'id': record.pk, 'date': str(record.ngay), 'start': '', 'end': '',
              'hours': ZERO, 'multiplier': ZERO, 'warnings': [], 'error': ''}
    if (record.trang_thai != 'present' or not record.gio_vao or not record.gio_ra
            or record.gio_ra <= record.gio_vao or record.ngay < record.nhan_vien.hire_date):
        return result
    period = period or KyCong.objects.filter(nam=record.ngay.year, thang=record.ngay.month).first()
    day = day or LichLamViec.objects.filter(ngay=record.ngay).first()
    if not period or not day:
        result['error'] = 'Thiếu cấu hình kỳ công hoặc lịch ngày để xác định OT.'
        return result
    start = max(record.gio_vao, time(17)) if day.loai_ngay == 'work' else record.gio_vao
    end = record.gio_ra
    if start >= end:
        return result
    hours = interval_hours(record.ngay, start, end)
    if day.loai_ngay != 'work':
        lunch_start, lunch_end = max(start, period.bat_dau_nghi_trua), min(end, period.ket_thuc_nghi_trua)
        if lunch_start < lunch_end:
            hours -= interval_hours(record.ngay, lunch_start, lunch_end)
    result.update(start=str(start), end=str(end), hours=max(ZERO, hours),
                  multiplier={'work': Decimal('1.5'), 'rest': Decimal(2), 'holiday': Decimal(3)}[day.loai_ngay])
    if hours and (start < time(6) or end > time(22)):
        result['error'] = 'Có giờ ban đêm (22:00–06:00); chưa hỗ trợ công thức OT ban đêm. Cần đối soát trước khi tính lương.'
    normal = min(period.gio_chuan * day.cong_chuan, period.gio_chuan)
    if (day.loai_ngay == 'work' and hours > normal / 2) or hours + record.so_gio_lam > 12:
        result['warnings'].append('Vượt giới hạn giờ làm thêm trong ngày; giữ nguyên giờ thực tế, cần kiểm tra tổ chức lao động.')
    return result


def payroll_overtime(employee, year, month):
    period = KyCong.objects.filter(nam=year, thang=month).first()
    days = {day.ngay: day for day in LichLamViec.objects.filter(ngay__year=year, ngay__month=month)}
    rows = []
    for record in ChamCong.objects.filter(nhan_vien=employee, ngay__year=year, ngay__month=month).select_related('nhan_vien').order_by('ngay'):
        item = automatic_overtime(record, period, days.get(record.ngay))
        if item['error']:
            raise ValidationError(f"{record.ngay}: {item['error']}")
        if item['hours']:
            rows.append(item)
    monthly = sum((item['hours'] for item in rows), ZERO)
    annual = ZERO
    periods = {(p.nam, p.thang): p for p in KyCong.objects.filter(nam=year)}
    year_days = {d.ngay: d for d in LichLamViec.objects.filter(ngay__year=year)}
    for record in ChamCong.objects.filter(nhan_vien=employee, ngay__year=year).select_related('nhan_vien'):
        annual += automatic_overtime(record, periods.get((year, record.ngay.month)), year_days.get(record.ngay))['hours']
    if rows and monthly > 40:
        rows[0]['warnings'].append('Vượt 40 giờ OT/tháng; không tự cắt giờ hoặc tiền đã làm.')
    if rows and annual > 200:
        rows[0]['warnings'].append('Vượt ngưỡng mặc định 200 giờ OT/năm; cần kiểm tra điều kiện ngoại lệ theo pháp luật.')
    return rows


def calculate_record(record, period):
    record.full_clean()
    calendar = LichLamViec.objects.filter(ngay=record.ngay).first()
    if calendar is None:
        raise ValidationError('Chưa cấu hình lịch cho ngày này.')
    record.so_gio_lam = Decimal(0)
    record.cong_thuc_te = Decimal(0)
    record.so_phut_tre = 0
    if record.gio_vao and record.gio_ra:
        at = lambda value: datetime.combine(record.ngay, value)
        start = max(at(record.gio_vao), at(period.gio_bat_dau))
        end = min(at(record.gio_ra), at(period.gio_ket_thuc), at(time(17)))
        seconds = max(0, int((end - start).total_seconds()))
        lunch = max(0, int((min(end, at(period.ket_thuc_nghi_trua)) - max(start, at(period.bat_dau_nghi_trua))).total_seconds()))
        if calendar.loai_ngay == 'work':
            record.so_gio_lam = Decimal(max(0, seconds - lunch)) / Decimal(3600)
            record.cong_thuc_te = min(calendar.cong_chuan, record.so_gio_lam / period.gio_chuan)
            # Phút thực tế, làm tròn lên khi có giây; không tạo khoản phạt tiền.
            late_seconds = max(0, int((at(record.gio_vao) - at(period.gio_bat_dau)).total_seconds()))
            record.so_phut_tre = (late_seconds + 59) // 60
    leave = LeaveDay.objects.filter(employee=record.nhan_vien, date=record.ngay, approved=True).first()
    record.cong_nghi_co_luong = leave.units if leave and leave.paid else Decimal(0)
    if leave and record.cong_thuc_te + leave.units > calendar.cong_chuan:
        raise ValidationError('Công thực tế và nghỉ phép vượt công chuẩn ngày; cần kiểm tra dữ liệu.')
    record.tong_cong = record.cong_thuc_te + record.cong_nghi_co_luong
    if record.trang_thai == 'leave' and not leave:
        raise ValidationError('Chưa có nghỉ phép được duyệt cho ngày này.')
    for field in ['so_gio_lam', 'cong_thuc_te', 'cong_nghi_co_luong', 'tong_cong']:
        setattr(record, field, getattr(record, field).quantize(Decimal('0.0001')))
    record.so_gio_tang_ca = automatic_overtime(record, period, calendar)['hours']
    return record
