from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class Bonus(models.Model):
    employee = models.ForeignKey('employees.Employee', on_delete=models.PROTECT)
    month = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    year = models.PositiveSmallIntegerField(validators=[MinValueValidator(2000), MaxValueValidator(2100)])
    name = models.CharField('Khoản thưởng', max_length=150)
    amount = models.DecimalField('Số tiền', max_digits=16, decimal_places=2, validators=[MinValueValidator(0)])
    status = models.CharField('Trạng thái', max_length=10,
                             choices=[('pending', 'Chờ duyệt'), ('approved', 'Đã duyệt')], default='pending')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.PROTECT)
    approved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.employee}: {self.name}'
