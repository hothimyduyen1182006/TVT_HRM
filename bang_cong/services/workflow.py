"""Lưu, duyệt và mở lại công; dùng chung kiểm tra khóa kỳ và ghi lịch sử."""
import calendar
from datetime import date
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from nhan_vien.access import require_role, HR, DIRECTOR
from nhan_vien.models import Employee
from bang_cong.models import KyCong, ChamCong, NhatKyCong, LichLamViec
from bang_cong.models import ChotBangCong
from .calculations import calculate_record
from .scheduling import validate_schedule
from .summaries import record_adjustments, refresh_summary, refresh_period_summaries


def period_is_locked(period, employee_id, record_date=None):
    if not period:
        return False
    if period.trang_thai == 'approved':
        return True
    approval = period.employee_approvals.filter(nhan_vien_id=employee_id).only('ngay_duyet').first()
    if not approval:
        return False
    if record_date is None:
        return not ChamCong.objects.filter(nhan_vien_id=employee_id,
            ngay__year=period.nam, ngay__month=period.thang,
            ngay_cap_nhat__gt=approval.ngay_duyet).exists()
    # An employee approval locks only completed rows included in that approval.
    return ChamCong.objects.filter(nhan_vien_id=employee_id, ngay=record_date).exclude(
        trang_thai='incomplete').filter(ngay_cap_nhat__lte=approval.ngay_duyet).exists()


def record_is_locked(record):
    period = KyCong.objects.filter(nam=record.ngay.year, thang=record.ngay.month).first()
    return period_is_locked(period, record.nhan_vien_id, record.ngay)


def _recalculate_records(records, period, actor, reason):
    """Tính lại công và ghi lịch sử bằng cùng một luồng khi duyệt kỳ hoặc nhân viên."""
    for record in records:
        before = record_values(record)
        calculate_record(record, period)
        record.save()
        after = record_values(record)
        if before != after:
            audit = NhatKyCong.objects.create(nguoi_thuc_hien=actor, hanh_dong='recalculate', ly_do=reason,
                du_lieu_cu=before, du_lieu_moi=after)
            record_adjustments(audit)


def record_values(record):
    # Giữ khóa JSON lịch sử để đối chiếu phiếu lương và nhật ký cũ.
    fields = {
        'pk': 'pk', 'employee_id': 'nhan_vien_id', 'date': 'ngay',
        'check_in': 'gio_vao', 'check_out': 'gio_ra', 'status': 'trang_thai',
        'work_hours': 'so_gio_lam', 'late_minutes': 'so_phut_tre',
        'actual_units': 'cong_thuc_te', 'paid_leave_units': 'cong_nghi_co_luong',
        'paid_units': 'tong_cong', 'overtime_hours': 'gio_tang_ca', 'note': 'ghi_chu',
    }
    return {key: str(getattr(record, field)) for key, field in fields.items()}


@transaction.atomic
def save_record(actor, record, reason):
    require_role(actor, HR, DIRECTOR)
    if not reason.strip():
        raise ValidationError('Cần lý do thay đổi.')
    period = KyCong.objects.select_for_update().get(nam=record.ngay.year, thang=record.ngay.month)
    if period_is_locked(period, record.nhan_vien_id, record.ngay):
        raise ValidationError('Kỳ công đã duyệt, cần mở lại trước.')
    before = {}
    if record.pk:
        old = ChamCong.objects.select_for_update().get(pk=record.pk)
        if old.nhan_vien_id != record.nhan_vien_id or old.ngay != record.ngay:
            raise ValidationError('Không đổi nhân viên/ngày của bản ghi đã tạo.')
        before = record_values(old)
    record.nguoi_cap_nhat = actor
    calculate_record(record, period)
    record.full_clean()
    record.save()
    after = record_values(record)
    if not before:
        NhatKyCong.objects.create(nguoi_thuc_hien=actor, hanh_dong='create_record', ly_do=reason, du_lieu_cu={}, du_lieu_moi=after)
    elif before != after:
        audit = NhatKyCong.objects.create(nguoi_thuc_hien=actor, hanh_dong='edit_record', ly_do=reason, du_lieu_cu=before, du_lieu_moi=after)
        record_adjustments(audit)
    refresh_summary(record.nhan_vien, period)
    return record


@transaction.atomic
def change_period(actor, period_id, action, reason):
    require_role(actor, DIRECTOR)
    period = KyCong.objects.select_for_update().get(pk=period_id)
    if not reason.strip():
        raise ValidationError('Cần ghi lý do.')
    before = {'period': period.pk, 'status': period.trang_thai, 'revision': period.phien_ban}
    if action == 'approve':
        if period.trang_thai != 'pending':
            raise ValidationError('Kỳ công phải đang chờ duyệt.')
        validate_schedule(period)
        days = calendar.monthrange(period.nam, period.thang)[1]
        configured = LichLamViec.objects.filter(ngay__year=period.nam, ngay__month=period.thang)
        if configured.count() != days:
            raise ValidationError('Phải cấu hình lịch cho tất cả ngày trong tháng.')
        records = ChamCong.objects.filter(ngay__year=period.nam, ngay__month=period.thang)
        employees = Employee.objects.filter(is_active=True, hire_date__lte=date(period.nam, period.thang, days))
        for employee in employees:
            required = configured.filter(loai_ngay='work', ngay__gte=employee.hire_date).values_list('ngay', flat=True)
            available = set(records.filter(nhan_vien=employee).exclude(trang_thai='incomplete').values_list('ngay', flat=True))
            if not set(required).issubset(available):
                raise ValidationError(f'{employee}: còn ngày làm việc chưa kiểm tra.')
        _recalculate_records(records, period, actor, reason)
        period.trang_thai = 'approved'
        period.ds_nhan_vien = list(employees.values_list('pk', flat=True))
        for employee in employees:
            ChotBangCong.objects.get_or_create(ky_cong=period, nhan_vien=employee, defaults={'nguoi_duyet': actor})
        period.nguoi_duyet = actor
        period.ngay_duyet = timezone.now()
    elif action == 'reopen':
        if period.trang_thai != 'approved':
            raise ValidationError('Chỉ mở lại kỳ đã duyệt.')
        from bang_luong.models import PayrollPeriod
        if PayrollPeriod.objects.filter(attendance_period=period).filter(
                Q(status__in=['approved', 'paid']) | Q(records__status__in=['approved', 'paid'])).exists():
            raise ValidationError('Cần mở lại bảng lương trước; lương đã chi trả không mở lại trực tiếp.')
        period.trang_thai = 'pending'
        period.phien_ban += 1
        period.nguoi_duyet = None
        period.ngay_duyet = None
        period.employee_approvals.all().delete()
    else:
        raise ValidationError('Thao tác không hợp lệ.')
    period.save()
    refresh_period_summaries(period)
    NhatKyCong.objects.create(nguoi_thuc_hien=actor, hanh_dong=action, ly_do=reason, du_lieu_cu=before,
                                      du_lieu_moi={'period': period.pk, 'status': period.trang_thai, 'revision': period.phien_ban})
    if action == 'approve':
        from bang_luong.services.calculations import refresh_employee_payroll
        for employee_id in period.ds_nhan_vien:
            refresh_employee_payroll(actor, employee_id, period.nam, period.thang)


@transaction.atomic
def approve_employee(actor, employee, period_id):
    require_role(actor, HR, DIRECTOR)
    period = KyCong.objects.select_for_update().get(pk=period_id)
    if period_is_locked(period, employee.pk):
        raise ValidationError('Bảng công nhân viên này đã được duyệt.')
    validate_schedule(period)
    days = calendar.monthrange(period.nam, period.thang)[1]
    schedules = LichLamViec.objects.filter(ngay__year=period.nam, ngay__month=period.thang)
    if schedules.count() != days:
        raise ValidationError('Phải cấu hình lịch đủ tháng trước khi duyệt.')
    records = ChamCong.objects.filter(nhan_vien=employee, ngay__year=period.nam, ngay__month=period.thang)
    required = set(schedules.filter(loai_ngay='work', ngay__gte=employee.hire_date).values_list('ngay', flat=True))
    available = set(records.exclude(trang_thai='incomplete').values_list('ngay', flat=True))
    if not records.exists() or not required.issubset(available) or records.filter(trang_thai='incomplete').exists():
        raise ValidationError('Bảng công nhân viên còn thiếu ngày hoặc có dữ liệu chưa kiểm tra.')
    _recalculate_records(records, period, actor, 'Tính lại trước khi duyệt nhân viên')
    approval = period.employee_approvals.filter(nhan_vien=employee).first()
    if approval:
        approval.nguoi_duyet = actor
        approval.ngay_duyet = timezone.now()
        approval.save(update_fields=['nguoi_duyet', 'ngay_duyet'])
    else:
        approval = ChotBangCong.objects.create(ky_cong=period, nhan_vien=employee, nguoi_duyet=actor)
    NhatKyCong.objects.create(nguoi_thuc_hien=actor, hanh_dong='approve_employee', ly_do='Duyệt công nhân viên từ trang chi tiết chấm công',
        du_lieu_cu={'approval_status': 'pending'}, du_lieu_moi={'employee_id': str(employee.pk),
            'date': f'{period.nam:04}-{period.thang:02}-01', 'approval_status': 'approved'})
    employee_ids = set(Employee.objects.filter(is_active=True,
        hire_date__lte=date(period.nam, period.thang, days)).values_list('pk', flat=True))
    current_approval_ids = set()
    for employee_approval in period.employee_approvals.all():
        if not ChamCong.objects.filter(nhan_vien_id=employee_approval.nhan_vien_id,
                ngay__year=period.nam, ngay__month=period.thang,
                ngay_cap_nhat__gt=employee_approval.ngay_duyet).exists():
            current_approval_ids.add(employee_approval.nhan_vien_id)
    if employee_ids and employee_ids.issubset(current_approval_ids):
        period.trang_thai = 'approved'
        period.ds_nhan_vien = sorted(employee_ids)
        period.nguoi_duyet = actor
        period.ngay_duyet = timezone.now()
        period.save()
        NhatKyCong.objects.create(nguoi_thuc_hien=actor, hanh_dong='approve', ly_do='Tất cả nhân viên trong kỳ đã được duyệt riêng',
            du_lieu_cu={'period': period.pk, 'status': 'pending'}, du_lieu_moi={'period': period.pk, 'status': 'approved', 'revision': period.phien_ban})
    refresh_summary(employee, period)
    from bang_luong.services.calculations import refresh_employee_payroll
    approval.payroll_error = refresh_employee_payroll(actor, employee.pk, period.nam, period.thang)
    return approval
