from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


FULL_DAY_UNITS = Decimal('1.0000')
ANNUAL_LEAVE_DAYS = 12


def annual_leave_days_used(employee, year, exclude_request_id=None):
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    requests = LeaveRequest.objects.filter(
        employee=employee,
        leave_type='annual',
        Trang_thai__in=('pending', 'approved'),
        Ngay_bat_dau__lte=year_end,
        Ngay_ket_thuc__gte=year_start,
    )
    if exclude_request_id is not None:
        requests = requests.exclude(pk=exclude_request_id)

    used_dates = set()
    for request in requests.only('Ngay_bat_dau', 'Ngay_ket_thuc'):
        start = max(request.Ngay_bat_dau, year_start)
        end = min(request.Ngay_ket_thuc, year_end)
        for day_offset in range((end - start).days + 1):
            used_dates.add(start + timedelta(days=day_offset))
    return len(used_dates)


class LeaveDay(models.Model):
    """Ngày nghỉ đã duyệt, được bảng công và bảng lương dùng để tính công."""
    employee = models.ForeignKey('employees.Employee', on_delete=models.PROTECT)
    date = models.DateField('Ngày nghỉ')
    units = models.DecimalField(
        'Số công nghỉ',
        max_digits=5,
        decimal_places=4,
    )
    paid = models.BooleanField('Hưởng lương', default=False)
    reason = models.CharField('Lý do', max_length=255)
    approved = models.BooleanField('Đã duyệt', default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'date'],
                name='unique_employee_leave_day',
            ),
            models.CheckConstraint(check=models.Q(units=FULL_DAY_UNITS), name='leave_day_full_day_only'),
        ]

    def clean(self):
        if self.units != FULL_DAY_UNITS:
            raise ValidationError({'units': 'Mỗi ngày nghỉ phải tương đương 1 công.'})

        if self.approved and self.employee_id:
            # Import cục bộ để tránh phụ thuộc vòng với app bảng công.
            from bang_cong.models import ChotBangCong, KyCong

            periods = KyCong.objects.filter(
                nam=self.date.year,
                thang=self.date.month,
            )
            period_is_approved = periods.filter(trang_thai='approved').exists()
            employee_is_approved = ChotBangCong.objects.filter(
                ky_cong__in=periods,
                nhan_vien_id=self.employee_id,
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
    STATUS_CHOICES = [
        ('pending', 'Đang chờ'),
        ('approved', 'Đã duyệt'),
        ('rejected', 'Từ chối'),
    ]

    # Tên field và tên cột được giữ đồng nhất với cấu trúc database tiếng Việt.
    Ma_don = models.BigAutoField(primary_key=True)
    # employee vẫn là tên quan hệ trong Python; Ma_nguoi_dung là tên cột khóa ngoại.
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.PROTECT,
        related_name='leave_requests',
        db_column='Ma_nguoi_dung',
    )
    Ngay_bat_dau = models.DateField('Từ ngày')
    Ngay_ket_thuc = models.DateField('Đến ngày')
    leave_type = models.CharField(
        'Loại nghỉ',
        max_length=20,
        choices=LEAVE_TYPES,
        default='annual',
    )
    paid = models.BooleanField('Nghỉ hưởng lương', default=False)
    Ly_do = models.CharField('Lý do', max_length=255)
    Tep_dinh_kem = models.FileField(
        'Ảnh minh chứng',
        upload_to='leave_evidence/%Y/%m/',
        blank=True,
        null=True,
    )
    Trang_thai = models.CharField(
        'Trạng thái',
        max_length=12,
        choices=STATUS_CHOICES,
        default='pending',
    )
    review_note = models.TextField('Lý do từ chối', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='reviewed_leave_requests',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def days_count(self):
        return (self.Ngay_ket_thuc - self.Ngay_bat_dau).days + 1

    def clean(self):
        if (
            self.Ngay_bat_dau
            and self.Ngay_ket_thuc
            and self.Ngay_ket_thuc < self.Ngay_bat_dau
        ):
            raise ValidationError('Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.')

        if (
            self.employee_id
            and self.Ngay_bat_dau
            and self.Ngay_bat_dau < self.employee.hire_date
        ):
            raise ValidationError('Ngày nghỉ không được trước ngày vào làm.')

        if (
            self.employee_id
            and self.leave_type == 'annual'
            and self.Ngay_bat_dau
            and self.Ngay_ket_thuc
        ):
            for year in range(self.Ngay_bat_dau.year, self.Ngay_ket_thuc.year + 1):
                year_start = date(year, 1, 1)
                year_end = date(year, 12, 31)
                start = max(self.Ngay_bat_dau, year_start)
                end = min(self.Ngay_ket_thuc, year_end)
                requested_days = (end - start).days + 1
                used_days = annual_leave_days_used(self.employee, year, self.pk)
                if used_days + requested_days > ANNUAL_LEAVE_DAYS:
                    remaining = max(0, ANNUAL_LEAVE_DAYS - used_days)
                    raise ValidationError(
                        f'Năm {year} chỉ còn {remaining} ngày phép năm; hạn mức là {ANNUAL_LEAVE_DAYS} ngày.'
                    )
