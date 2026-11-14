from django.conf import settings
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


def complete_bonus_records(rows):
    """Use the same valid proposal rows in bonus views and payroll."""
    return rows.filter(
        Q(bonus_type__in=['attendance', 'seniority']) |
        Q(bonus_type='other', name__gt='', reason__gt='', proposed_at__isnull=False)
    )


def approved_bonus_records(rows):
    """Return complete, approved bonuses that are eligible for payroll."""
    return complete_bonus_records(rows).filter(
        status='approved', approved_by__isnull=False, approved_at__isnull=False
    )


def displayed_bonus_records(rows):
    """Keep approved historical rows visible so bonuses and payroll stay consistent."""
    return rows.filter(Q(pk__in=complete_bonus_records(rows).values('pk')) | Q(status='approved'))


def incomplete_approved_bonus_records(rows):
    return rows.filter(status='approved').exclude(pk__in=approved_bonus_records(rows).values('pk'))


def payroll_bonus_records(rows):
    """Never silently treat an invalid approved bonus as zero."""
    if incomplete_approved_bonus_records(rows).exists():
        raise ValidationError('Có khoản thưởng đã duyệt thiếu thông tin đề xuất hoặc phê duyệt. '
                              'Cần kiểm tra và hoàn thiện Bảng thưởng trước khi tính hoặc duyệt lương.')
    return approved_bonus_records(rows)


def tao_ma_tong_thuong():
    return 'T' + uuid4().hex[:24]


class TongThuong(models.Model):
    """Tổng thưởng theo nhân viên/kỳ, lưu nguồn đã dùng trong phiếu lương."""
    ma_thuong = models.CharField(max_length=25, unique=True, default=tao_ma_tong_thuong, editable=False)
    nhan_vien = models.ForeignKey('employees.Employee', on_delete=models.PROTECT)
    thang = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    nam = models.PositiveSmallIntegerField(validators=[MinValueValidator(2000), MaxValueValidator(2100)])
    tong_tien = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    chi_tiet = models.JSONField(default=list)

    class Meta:
        db_table = 'Tong_thuong'
        constraints = [models.UniqueConstraint(
            fields=['nhan_vien', 'nam', 'thang'], name='unique_employee_bonus_summary',
        )]


class Bonus(models.Model):
    TYPES = [
        ('attendance', 'Thưởng chuyên cần'),
        ('seniority', 'Thưởng thâm niên'),
        ('other', 'Thưởng khác'),
    ]
    STATUSES = [
        ('draft', 'Bản nháp'),
        ('pending', 'Chờ duyệt'),
        ('approved', 'Đã duyệt'),
        ('rejected', 'Từ chối'),
    ]
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
