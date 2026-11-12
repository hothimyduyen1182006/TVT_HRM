from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from nhan_vien.models import Employee
from bang_cong.models import ChamCong
from .calculations import calculate_record
from .workflow import period_is_locked
from .scheduling import ensure_clock_schedule


@transaction.atomic
def punch(actor, action, note=''):
    if not actor.is_authenticated:
        raise PermissionDenied('Cần đăng nhập trước khi chấm công.')
    if action not in ['in', 'out']:
        raise ValidationError('Thao tác không hợp lệ.')
    now = timezone.localtime().replace(microsecond=0)
    today = now.date()
    employee = Employee.objects.select_for_update().filter(user=actor, is_active=True).first()
    if not employee:
        raise PermissionDenied('Tài khoản chưa liên kết nhân viên đang làm việc.')
    if today < employee.hire_date:
        raise ValidationError('Chưa đến ngày vào làm.')
    period, day = ensure_clock_schedule(today, actor)
    if period_is_locked(period, employee.pk, today):
        raise ValidationError('Bảng công đã duyệt, không thể chấm công thêm.')
    if not day or day.loai_ngay != 'work':
        raise ValidationError('Hôm nay chưa có lịch làm việc thông thường được cấu hình.')
    record = ChamCong.objects.select_for_update().filter(nhan_vien=employee, ngay=today).first()
    if action == 'in':
        if record:
            raise ValidationError('Hôm nay đã có bản ghi chấm công. Không thể check-in lại.')
        record = ChamCong(nhan_vien=employee, ngay=today, gio_vao=now.time(), trang_thai='incomplete')
    elif action == 'out':
        if not record or not record.gio_vao:
            raise ValidationError('Bạn cần check-in trước.')
        if record.gio_ra or record.trang_thai != 'incomplete':
            raise ValidationError('Bản ghi đã kết thúc hoặc cần nhân sự kiểm tra.')
        if now.time() <= record.gio_vao:
            raise ValidationError('Giờ check-out phải sau giờ check-in.')
        if len(note) > 2000:
            raise ValidationError('Ghi chú tối đa 2000 ký tự.')
        record.gio_ra = now.time()
        record.trang_thai = 'present'
        record.ghi_chu = note.strip()
        calculate_record(record, period)
    record.nguoi_cap_nhat = actor
    record.full_clean()
    record.save()
    from .summaries import refresh_summary
    refresh_summary(employee, period)
    return record
