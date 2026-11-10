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


class OvertimeApproval(models.Model):
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

    def clean(self):
        from .services.calculations import validate_overtime
        if self.status != 'legacy':
            if (not self.requested_by_id or not self.requested_at or not self.request_reason.strip()
                    or not self.requested_hours):
                raise ValidationError('Yêu cầu OT thiếu thông tin gửi của nhân viên.')
            if self.employee_id and self.requested_by_id != self.employee.user_id:
                raise ValidationError('Nhân viên chỉ được gửi yêu cầu OT của bản thân.')
            if self.approved != (self.status == 'approved'):
                raise ValidationError('Trạng thái duyệt OT không nhất quán.')
            if self.status in ['approved', 'rejected'] and (not self.reviewed_by_id or not self.reviewed_at):
                raise ValidationError('Thiếu người hoặc thời điểm xử lý OT.')
            if self.status == 'approved' and self.hours and self.hours > self.requested_hours:
                raise ValidationError('Không được duyệt quá số giờ nhân viên đề nghị.')
            if self.status == 'approved' and (not self.approved_by_id or not self.approved_at):
                raise ValidationError('Thiếu người hoặc thời điểm phê duyệt OT.')
            if self.status == 'approved' and (self.approved_by_id != self.reviewed_by_id or self.approved_at != self.reviewed_at):
                raise ValidationError('Thông tin người và thời điểm duyệt OT không nhất quán.')
            if self.status == 'rejected' and not self.rejection_reason.strip():
                raise ValidationError('Cần ghi lý do từ chối OT.')
        validate_overtime(self)

    def save(self, *args, **kwargs):
        from django.core.exceptions import PermissionDenied
        from django.db import transaction
        from employees.models import Employee
        with transaction.atomic():
            if self.status == 'legacy':
                raise PermissionDenied('Dữ liệu OT cũ chỉ được xem, không tự chuyển thành yêu cầu mới.')
            Employee.objects.select_for_update().get(pk=self.employee_id)
            from .services.workflow import period_is_locked, can_approve_overtime
            period=AttendancePeriod.objects.select_for_update().filter(year=self.date.year,month=self.date.month).first()
            if not period or period_is_locked(period,self.employee_id):
                raise ValidationError('Kỳ công đã khóa hoặc chưa được cấu hình.')
            from payroll.models import PayrollPeriod
            if PayrollPeriod.objects.filter(attendance_period=period).filter(
                    models.Q(status__in=['approved','paid']) |
                    models.Q(records__employee_id=self.employee_id,records__status__in=['approved','paid'])).exists():
                raise ValidationError('Phiếu lương đã khóa; không được thay đổi OT.')
            if not self.pk and self.status != 'pending':
                raise PermissionDenied('Phải gửi yêu cầu chờ duyệt trước khi xử lý OT.')
            if self.pk:
                old = type(self).objects.select_for_update().get(pk=self.pk)
                if old.status != 'pending':
                    raise PermissionDenied('Yêu cầu đã xử lý không được sửa hoặc duyệt lại.')
                fields = ['employee_id','department_id','date','start_time','end_time','requested_hours',
                          'request_reason','requested_by_id','requested_at']
                if any(getattr(old, field) != getattr(self, field) for field in fields):
                    raise PermissionDenied('Không được thay đổi nội dung yêu cầu đã gửi.')
                if self.status not in ['approved','rejected'] or not self.reviewed_by_id or not can_approve_overtime(self.reviewed_by,self.employee):
                    raise PermissionDenied('Chỉ Trưởng phòng Sản xuất phụ trách được xử lý yêu cầu.')
            self.full_clean()
            return super().save(*args, **kwargs)

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
