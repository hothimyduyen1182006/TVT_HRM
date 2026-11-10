from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class AttendancePeriod(models.Model):
    month = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    year = models.PositiveSmallIntegerField(validators=[MinValueValidator(2000), MaxValueValidator(2100)])
    start_time = models.TimeField('Bắt đầu làm')
    lunch_start = models.TimeField('Bắt đầu nghỉ trưa')
    lunch_end = models.TimeField('Kết thúc nghỉ trưa')
    end_time = models.TimeField('Kết thúc làm')
    standard_hours = models.DecimalField('Giờ/công', max_digits=5, decimal_places=2,
                                        validators=[MinValueValidator(Decimal('0.01'))])
    policy_confirmed = models.BooleanField('Đã xác nhận chính sách và lịch cả tháng', default=False)
    status = models.CharField(max_length=10, choices=[('pending', 'Chờ duyệt'), ('approved', 'Đã duyệt')],
                              default='pending')
    revision = models.PositiveIntegerField(default=1)
    employee_ids = models.JSONField(default=list, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['year', 'month'], name='unique_attendance_period')]
        ordering = ['-year', '-month']

    def clean(self):
        if any(value is None for value in [self.start_time, self.lunch_start, self.lunch_end, self.end_time]):
            return
        if not self.start_time < self.lunch_start < self.lunch_end < self.end_time:
            raise ValidationError('Thứ tự giờ làm/nghỉ trưa không hợp lệ.')

    def __str__(self):
        return f'{self.month:02}/{self.year}'


class EmployeeAttendanceApproval(models.Model):
    period = models.ForeignKey(AttendancePeriod, on_delete=models.PROTECT, related_name='employee_approvals')
    employee = models.ForeignKey('employees.Employee', on_delete=models.PROTECT)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    approved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['period', 'employee'], name='unique_employee_attendance_approval')]


class WorkCalendarDay(models.Model):
    date = models.DateField('Ngày', unique=True)
    kind = models.CharField('Loại ngày', max_length=10,
                            choices=[('work', 'Làm việc'), ('rest', 'Nghỉ tuần'), ('holiday', 'Lễ')])
    expected_units = models.DecimalField('Công chuẩn', max_digits=5, decimal_places=4,
                                         validators=[MinValueValidator(0), MaxValueValidator(1)])
    name = models.CharField('Ghi chú', max_length=150, blank=True)

    def clean(self):
        if self.kind != 'work' and self.expected_units != 0:
            raise ValidationError('Ngày nghỉ/lễ phải có công chuẩn bằng 0.')


class AttendanceRecord(models.Model):
    employee = models.ForeignKey('employees.Employee', on_delete=models.PROTECT)
    date = models.DateField('Ngày')
    check_in = models.TimeField('Check-in', null=True, blank=True)
    check_out = models.TimeField('Check-out', null=True, blank=True)
    status = models.CharField('Trạng thái', max_length=15,
                              choices=[('present', 'Có mặt'), ('leave', 'Nghỉ phép'),
                                       ('absent', 'Nghỉ không phép'), ('incomplete', 'Thiếu dữ liệu')])
    work_hours = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    late_minutes = models.PositiveIntegerField(default=0)
    actual_units = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    paid_leave_units = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    paid_units = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    note = models.TextField('Ghi chú', blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', 'employee__code']
        constraints = [
            models.UniqueConstraint(fields=['employee', 'date'], name='unique_employee_attendance_date'),
            models.CheckConstraint(check=models.Q(check_out__isnull=True) | models.Q(check_in__isnull=True)
                                   | models.Q(check_out__gt=models.F('check_in')), name='valid_checkout'),
        ]

    def clean(self):
        if self.employee_id and self.date and self.date < self.employee.hire_date:
            raise ValidationError('Ngày công không được trước ngày vào làm.')
        open_shift = self.status == 'incomplete' and self.check_in and not self.check_out
        if bool(self.check_in) != bool(self.check_out) and not open_shift:
            raise ValidationError('Cần nhập đủ check-in/check-out hoặc để trống cả hai.')
        if self.check_in and self.check_out and self.check_out <= self.check_in:
            raise ValidationError('Check-out phải sau check-in trong cùng ngày.')
        if self.status == 'present' and not self.check_in:
            raise ValidationError('Có mặt cần đủ giờ vào và ra.')
        if self.status in ('leave', 'absent') and self.check_in:
            raise ValidationError('Có giờ làm hãy chọn Có mặt; nghỉ một phần ngày lấy từ module nghỉ phép.')
        if self.status == 'incomplete' and self.check_out:
            raise ValidationError('Có đủ giờ vào và ra hãy chọn Có mặt.')

    @property
    def overtime_hours(self):
        from .services.calculations import automatic_overtime
        return automatic_overtime(self)['hours']


class OvertimeApproval(models.Model):
    """Read-only archive of the retired request/review workflow, excluded from payroll."""
    start_time = models.TimeField('Bắt đầu OT', null=True, blank=True)
    end_time = models.TimeField('Kết thúc OT', null=True, blank=True)
    department = models.ForeignKey('employees.Department', null=True, blank=True,
        on_delete=models.PROTECT, related_name='overtime_requests', verbose_name='Phòng ban khi gửi')
    status = models.CharField('Trạng thái yêu cầu', max_length=10, default='legacy', choices=[
        ('legacy', 'Dữ liệu cũ'), ('pending', 'Chờ duyệt'), ('approved', 'Đã duyệt'), ('rejected', 'Từ chối')])
    requested_hours = models.DecimalField('Giờ OT đề nghị', max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0.01')), MaxValueValidator(24)])
    request_reason = models.TextField('Lý do tăng ca', blank=True)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name='submitted_overtime')
    requested_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name='reviewed_overtime')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField('Lý do từ chối', blank=True)
    employee = models.ForeignKey('employees.Employee', on_delete=models.PROTECT)
    date = models.DateField('Ngày OT')
    hours = models.DecimalField('Giờ được duyệt', max_digits=6, decimal_places=2,
                               validators=[MinValueValidator(Decimal('0.01')), MaxValueValidator(24)])
    multiplier = models.DecimalField('Hệ số', max_digits=5, decimal_places=2,
                                    validators=[MinValueValidator(1)])
    approved = models.BooleanField('Đã duyệt', default=False)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['employee', 'date', 'start_time', 'end_time'],
                                               name='unique_employee_ot_interval')]

    def save(self, *args, **kwargs):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('Lịch sử OT chỉ đọc. OT hiện tại tính tự động từ chấm công.')

    def delete(self, *args, **kwargs):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('Không được xóa lịch sử OT.')


class AttendanceAuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=30)
    reason = models.TextField()
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
