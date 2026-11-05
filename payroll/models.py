from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.db import models


class PayrollPeriod(models.Model):
    attendance_period = models.OneToOneField('attendance.AttendancePeriod', on_delete=models.PROTECT)
    status = models.CharField(max_length=10, default='pending',
                              choices=[('pending', 'Chờ duyệt'), ('approved', 'Đã duyệt'), ('paid', 'Đã chi trả')])
    attendance_revision = models.PositiveIntegerField(default=0)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                    related_name='approved_payrolls')
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                related_name='paid_payrolls')
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_evidence = models.TextField(blank=True)

    def __str__(self):
        return str(self.attendance_period)


class PayrollInput(models.Model):
    """Dữ liệu kỳ do nhân sự kiểm tra; thuế nhập theo kết quả tính có căn cứ."""
    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT)
    employee = models.ForeignKey('employees.Employee', on_delete=models.PROTECT)
    insurance_base = models.DecimalField('Lương đóng BH', max_digits=16, decimal_places=2,
                                         validators=[MinValueValidator(0)])
    insurance_rates = models.JSONField('Tỷ lệ BH (tên: tỷ lệ dạng thập phân)', default=dict, blank=True)
    tax_amount = models.DecimalField('Thuế TNCN đã xác định', max_digits=16, decimal_places=2,
                                     validators=[MinValueValidator(0)])
    tax_basis = models.TextField('Căn cứ thuế: chính sách kỳ, thu nhập, giảm trừ, người phụ thuộc')
    insurance_basis = models.TextField('Căn cứ BH: đối tượng, chính sách và kỳ áp dụng')
    verified = models.BooleanField('Đã kiểm tra đủ dữ liệu', default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['period', 'employee'], name='unique_payroll_input')]

    def clean(self):
        if self.period_id and self.employee_id and self.is_locked:
            raise ValidationError('Phiếu lương nhân viên đã duyệt, cần mở lại trước khi chỉnh đầu vào.')
        if not isinstance(self.insurance_rates, dict):
            raise ValidationError('Tỷ lệ BH phải là object JSON.')
        rate_total = Decimal(0)
        for name, rate in self.insurance_rates.items():
            try:
                value = Decimal(str(rate))
                if not name or not value.is_finite() or not 0 <= value <= 1:
                    raise ValueError
                rate_total += value
            except Exception:
                raise ValidationError('Tỷ lệ BH phải từ 0 đến 1; ví dụ {"BHXH": "0.08"}.')
        if rate_total > 1:
            raise ValidationError('Tổng tỷ lệ BH không được vượt 100%.')
        if not self.tax_basis.strip() or not self.insurance_basis.strip():
            raise ValidationError('Phải ghi căn cứ thuế và BH, kể cả trường hợp không áp dụng.')

    @property
    def is_locked(self):
        return self.period.status != 'pending' or PayrollRecord.objects.filter(
            period_id=self.period_id, employee_id=self.employee_id, status__in=['approved', 'paid']).exists()


class PayrollAdjustment(models.Model):
    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT)
    employee = models.ForeignKey('employees.Employee', on_delete=models.PROTECT)
    name = models.CharField('Tên khoản', max_length=150)
    kind = models.CharField('Loại', max_length=15,
                            choices=[('allowance', 'Phụ cấp'), ('deduction', 'Khấu trừ')])
    amount = models.DecimalField('Số tiền', max_digits=16, decimal_places=2, validators=[MinValueValidator(0)])
    basis = models.TextField('Căn cứ; khấu trừ không được trùng phần thời gian đã giảm công')
    approved = models.BooleanField('Đã duyệt', default=False)

    @property
    def is_locked(self):
        return self.period.status != 'pending' or PayrollRecord.objects.filter(
            period_id=self.period_id, employee_id=self.employee_id, status__in=['approved', 'paid']).exists()

    def clean(self):
        if self.period_id and self.employee_id and self.is_locked:
            raise ValidationError('Phiếu lương nhân viên đã duyệt, cần mở lại trước khi chỉnh khoản tiền.')


class PayrollRecord(models.Model):
    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name='records')
    employee = models.ForeignKey('employees.Employee', on_delete=models.PROTECT)
    status = models.CharField(max_length=10, default='pending', choices=[
        ('pending', 'Chờ duyệt'), ('approved', 'Đã duyệt'), ('paid', 'Đã chi trả')])
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='approved_salary_records')
    approved_at = models.DateTimeField(null=True, blank=True)
    employee_code = models.CharField(max_length=30)
    employee_name = models.CharField(max_length=150)
    department_id_snapshot = models.PositiveBigIntegerField()
    department_name = models.CharField(max_length=150)
    base_salary = models.DecimalField(max_digits=18, decimal_places=2)
    standard_units = models.DecimalField(max_digits=10, decimal_places=4)
    paid_units = models.DecimalField(max_digits=10, decimal_places=4)
    leave_units = models.DecimalField(max_digits=10, decimal_places=4)
    late_minutes = models.PositiveIntegerField()
    ot_hours = models.DecimalField(max_digits=10, decimal_places=4)
    attendance_pay = models.DecimalField(max_digits=24, decimal_places=8)
    ot_pay = models.DecimalField(max_digits=24, decimal_places=8)
    bonus_pay = models.DecimalField(max_digits=24, decimal_places=8)
    allowance = models.DecimalField(max_digits=24, decimal_places=8)
    insurance = models.DecimalField(max_digits=24, decimal_places=8)
    tax = models.DecimalField(max_digits=24, decimal_places=8)
    deductions = models.DecimalField(max_digits=24, decimal_places=8)
    net_pay = models.DecimalField(max_digits=18, decimal_places=0)
    breakdown = models.JSONField()
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['period', 'employee'], name='unique_payroll_record')]
        ordering = ['employee_code']


class PayrollAuditLog(models.Model):
    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=30)
    reason = models.TextField()
    snapshot = models.JSONField(default=list)


class PayrollExportLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    month = models.PositiveSmallIntegerField()
    year = models.PositiveSmallIntegerField()
    scope = models.JSONField()
    format = models.CharField(max_length=4)
