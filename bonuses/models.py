from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class Bonus(models.Model):
    TYPES = [('attendance', 'Thưởng chuyên cần'), ('seniority', 'Thưởng thâm niên'), ('other', 'Thưởng khác')]
    STATUSES = [('draft', 'Bản nháp'), ('pending', 'Chờ duyệt'), ('approved', 'Đã duyệt'), ('rejected', 'Từ chối')]
    employee = models.ForeignKey('employees.Employee', on_delete=models.PROTECT)
    month = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    year = models.PositiveSmallIntegerField(validators=[MinValueValidator(2000), MaxValueValidator(2100)])
    name = models.CharField('Khoản thưởng', max_length=150)
    bonus_type = models.CharField('Loại thưởng', max_length=20, choices=TYPES, default='other')
    reason = models.TextField('Lý do')
    proposed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='bonus_proposals')
    proposed_at = models.DateTimeField(blank=False, null=True)
    amount = models.DecimalField('Số tiền', max_digits=16, decimal_places=2, validators=[MinValueValidator(0)])
    status = models.CharField('Trạng thái', max_length=10, choices=STATUSES, default='pending')
    rejection_reason = models.TextField('Lý do từ chối', blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.PROTECT)
    approved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.employee}: {self.name}'
