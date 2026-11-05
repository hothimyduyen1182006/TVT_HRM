from decimal import Decimal
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
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
        constraints = [models.UniqueConstraint(fields=['employee', 'date'], name='unique_employee_leave_day')]

    def clean(self):
        if self.approved and self.employee_id:
            from attendance.models import AttendancePeriod, EmployeeAttendanceApproval
            periods = AttendancePeriod.objects.filter(year=self.date.year, month=self.date.month)
            if periods.filter(status='approved').exists() or EmployeeAttendanceApproval.objects.filter(period__in=periods, employee_id=self.employee_id).exists():
                raise ValidationError('Kỳ công đã duyệt. Cần mở lại trước khi sửa nghỉ phép.')
