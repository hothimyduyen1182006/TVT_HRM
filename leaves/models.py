from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class LeaveDay(models.Model):
    employee = models.ForeignKey('employees.Employee', on_delete=models.PROTECT)
    date = models.DateField('Ngày nghỉ')
    units = models.DecimalField('Số công nghỉ', max_digits=5, decimal_places=4,
                                validators=[MinValueValidator(Decimal('0.0001')), MaxValueValidator(1)])
    paid = models.BooleanField('Hưởng lương', default=False)
    reason = models.CharField('Lý do', max_length=255)
    approved = models.BooleanField('Đã duyệt', default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'date'],
                name='unique_employee_leave_day',
            ),
        ]

    def clean(self):
        if self.approved and self.employee_id:
            from attendance.models import AttendancePeriod, EmployeeAttendanceApproval
            periods = AttendancePeriod.objects.filter(
                year=self.date.year,
                month=self.date.month,
            )
            period_is_approved = periods.filter(status='approved').exists()
            employee_is_approved = EmployeeAttendanceApproval.objects.filter(
                period__in=periods,
                employee_id=self.employee_id,
            ).exists()
            if period_is_approved or employee_is_approved:
                raise ValidationError('Kỳ công đã duyệt. Cần mở lại trước khi sửa nghỉ phép.')


class LeaveRequest(models.Model):
    LEAVE_TYPES = [
        ('annual', 'Nghỉ phép năm'),
        ('sick', 'Nghỉ ốm'),
        ('personal', 'Việc riêng'),
        ('unpaid', 'Nghỉ không lương'),
    ]
    employee = models.ForeignKey('employees.Employee', on_delete=models.PROTECT, related_name='leave_requests')
    start_date = models.DateField('Từ ngày')
    end_date = models.DateField('Đến ngày')
    units = models.DecimalField('Số công mỗi ngày', max_digits=5, decimal_places=4,
                                default=Decimal('1.0000'),
                                validators=[MinValueValidator(Decimal('0.0001')), MaxValueValidator(1)])
    leave_type = models.CharField('Loại nghỉ', max_length=20, choices=LEAVE_TYPES, default='annual')
    paid = models.BooleanField('Nghỉ hưởng lương', default=False)
    reason = models.CharField('Lý do', max_length=255)
    evidence = models.FileField('Ảnh minh chứng', upload_to='leave_evidence/%Y/%m/', blank=True, null=True)
    status = models.CharField(
        'Trạng thái',
        max_length=12,
        choices=[('pending', 'Đang chờ'), ('approved', 'Đã duyệt'), ('rejected', 'Từ chối')],
        default='pending',
    )
    review_note = models.TextField('Lý do từ chối', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                    related_name='reviewed_leave_requests')
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError('Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.')
        if self.employee_id and self.start_date and self.start_date < self.employee.hire_date:
            raise ValidationError('Ngày nghỉ không được trước ngày vào làm.')
