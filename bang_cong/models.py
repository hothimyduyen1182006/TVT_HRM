from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class KyCong(models.Model):
    # Ca làm việc và lịch áp dụng cho một tháng.
    thang = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    nam = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(2000), MaxValueValidator(2100)],
    )
    gio_bat_dau = models.TimeField('Bắt đầu làm')
    bat_dau_nghi_trua = models.TimeField('Bắt đầu nghỉ trưa')
    ket_thuc_nghi_trua = models.TimeField('Kết thúc nghỉ trưa')
    gio_ket_thuc = models.TimeField('Kết thúc làm')
    gio_chuan = models.DecimalField(
        'Giờ/công', max_digits=5, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    trang_thai = models.CharField(
        max_length=10,
        choices=[('pending', 'Chờ duyệt'), ('approved', 'Đã duyệt')],
        default='pending',
    )
    phien_ban = models.PositiveIntegerField(default=1)
    ds_nhan_vien = models.JSONField(default=list, blank=True)
    nguoi_duyet = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
    )
    ngay_duyet = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['nam', 'thang'], name='unique_attendance_period',
            ),
        ]
        ordering = ['-nam', '-thang']

    def clean(self):
        gio_lam_viec = (
            self.gio_bat_dau,
            self.bat_dau_nghi_trua,
            self.ket_thuc_nghi_trua,
            self.gio_ket_thuc,
        )
        if any(gio is None for gio in gio_lam_viec):
            return
        if not (
            self.gio_bat_dau
            < self.bat_dau_nghi_trua
            < self.ket_thuc_nghi_trua
            < self.gio_ket_thuc
        ):
            raise ValidationError('Thứ tự giờ làm/nghỉ trưa không hợp lệ.')

    def __str__(self):
        return f'{self.thang:02}/{self.nam}'


class ChotBangCong(models.Model):
    # Một nhân viên chỉ có một kết quả duyệt trong mỗi kỳ.
    ky_cong = models.ForeignKey(
        KyCong, on_delete=models.PROTECT, related_name='employee_approvals',
    )
    nhan_vien = models.ForeignKey('employees.Employee', on_delete=models.PROTECT)
    tong_hop = models.OneToOneField(
        'TongHopCong', on_delete=models.PROTECT,
        null=True, blank=True, related_name='approval', verbose_name='Bản tổng hợp công',
    )
    nguoi_duyet = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
    )
    ngay_duyet = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'Chot_bang_cong'
        constraints = [
            models.UniqueConstraint(
                fields=['ky_cong', 'nhan_vien'],
                name='unique_employee_attendance_approval',
            ),
        ]

    def clean(self):
        if not self.tong_hop_id:
            return
        khoa_tong_hop = (self.tong_hop.ky_cong_id, self.tong_hop.nhan_vien_id)
        khoa_ban_chot = (self.ky_cong_id, self.nhan_vien_id)
        if khoa_tong_hop != khoa_ban_chot:
            raise ValidationError('Bản chốt phải thuộc đúng nhân viên và kỳ tổng hợp.')


class LichLamViec(models.Model):
    ngay = models.DateField('Ngày', unique=True)
    loai_ngay = models.CharField(
        'Loại ngày', max_length=10,
        choices=[('work', 'Làm việc'), ('rest', 'Nghỉ tuần'), ('holiday', 'Lễ')],
    )
    cong_chuan = models.DecimalField(
        'Công chuẩn', max_digits=5, decimal_places=4,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    ghi_chu = models.CharField('Ghi chú', max_length=150, blank=True)

    def clean(self):
        if self.loai_ngay != 'work' and self.cong_chuan != 0:
            raise ValidationError('Ngày nghỉ/lễ phải có công chuẩn bằng 0.')


class ChamCong(models.Model):
    # Dữ liệu gốc của nhân viên trong ngày.
    nhan_vien = models.ForeignKey('employees.Employee', on_delete=models.PROTECT)
    ngay = models.DateField('Ngày')
    gio_vao = models.TimeField('Check-in', null=True, blank=True)
    gio_ra = models.TimeField('Check-out', null=True, blank=True)
    trang_thai = models.CharField(
        'Trạng thái', max_length=15,
        choices=[
            ('present', 'Có mặt'),
            ('leave', 'Nghỉ phép'),
            ('absent', 'Nghỉ không phép'),
            ('incomplete', 'Thiếu dữ liệu'),
        ],
    )

    # Kết quả tính công được cập nhật qua services.
    so_gio_lam = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    so_phut_tre = models.PositiveIntegerField(default=0)
    cong_thuc_te = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    cong_nghi_co_luong = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    tong_cong = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    so_gio_tang_ca = models.DecimalField(
        'Giờ tăng ca', db_column='So_gio_tang_ca',
        max_digits=12, decimal_places=4, default=0,
    )

    ghi_chu = models.TextField('Ghi chú', blank=True)
    nguoi_cap_nhat = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT,
    )
    ngay_cap_nhat = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Cham_cong'
        ordering = ['-ngay', 'nhan_vien__code']
        constraints = [
            models.UniqueConstraint(
                fields=['nhan_vien', 'ngay'], name='unique_employee_attendance_date',
            ),
            models.CheckConstraint(
                check=(
                    models.Q(gio_ra__isnull=True)
                    | models.Q(gio_vao__isnull=True)
                    | models.Q(gio_ra__gt=models.F('gio_vao'))
                ),
                name='valid_checkout',
            ),
        ]

    def clean(self):
        if self.nhan_vien_id and self.ngay and self.ngay < self.nhan_vien.hire_date:
            raise ValidationError('Ngày công không được trước ngày vào làm.')
        ca_dang_mo = (
            self.trang_thai == 'incomplete' and self.gio_vao and not self.gio_ra
        )
        if bool(self.gio_vao) != bool(self.gio_ra) and not ca_dang_mo:
            raise ValidationError('Cần nhập đủ check-in/check-out hoặc để trống cả hai.')
        if self.gio_vao and self.gio_ra and self.gio_ra <= self.gio_vao:
            raise ValidationError('Check-out phải sau check-in trong cùng ngày.')
        if self.trang_thai == 'present' and not self.gio_vao:
            raise ValidationError('Có mặt cần đủ giờ vào và ra.')
        if self.trang_thai in ('leave', 'absent') and self.gio_vao:
            raise ValidationError(
                'Có giờ làm hãy chọn Có mặt; nghỉ một phần ngày lấy từ module nghỉ phép.'
            )
        if self.trang_thai == 'incomplete' and self.gio_ra:
            raise ValidationError('Có đủ giờ vào và ra hãy chọn Có mặt.')

    @property
    def gio_tang_ca(self):
        from .services.calculations import automatic_overtime

        return automatic_overtime(self)['hours']


class NhatKyCong(models.Model):
    nguoi_thuc_hien = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    ngay_tao = models.DateTimeField(auto_now_add=True)
    hanh_dong = models.CharField(max_length=30)
    ly_do = models.TextField()
    du_lieu_cu = models.JSONField(default=dict)
    du_lieu_moi = models.JSONField(default=dict)


class TongHopCong(models.Model):
    """Kết quả tổng hợp một nhân viên/tháng; chỉ cập nhật qua services."""

    ky_cong = models.ForeignKey(
        KyCong, on_delete=models.CASCADE, related_name='summaries',
    )
    nhan_vien = models.ForeignKey(
        'employees.Employee', on_delete=models.CASCADE,
        related_name='attendance_summaries',
    )
    thang = models.PositiveSmallIntegerField()
    nam = models.PositiveSmallIntegerField()
    cong_chuan = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    cong_thuc_te = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    cong_nghi_co_luong = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    so_ngay_khong_phep = models.PositiveIntegerField(default=0)
    tong_cong = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    so_gio_lam = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    gio_tang_ca = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    so_lan_tre = models.PositiveIntegerField(default=0)
    so_phut_tre = models.PositiveIntegerField(default=0)
    trang_thai = models.CharField(
        max_length=12, default='pending',
        choices=[
            ('pending', 'Chờ duyệt'),
            ('approved', 'Đã duyệt'),
            ('incomplete', 'Cần kiểm tra'),
            ('empty', 'Chưa có dữ liệu'),
        ],
    )
    ngay_cap_nhat = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Tong_hop_cong'
        constraints = [
            models.UniqueConstraint(
                fields=['nhan_vien', 'nam', 'thang'],
                name='unique_employee_month_summary',
            ),
            models.UniqueConstraint(
                fields=['ky_cong', 'nhan_vien'],
                name='unique_employee_period_summary',
            ),
        ]

    def clean(self):
        if self.ky_cong_id and (self.nam, self.thang) != (self.ky_cong.nam, self.ky_cong.thang):
            raise ValidationError('Tháng/năm tổng hợp phải khớp kỳ công.')


class LichSuDieuChinhCong(models.Model):
    """Một dòng cho một trường thay đổi; giữ liên kết nhật ký gốc để đối chiếu."""

    nhat_ky = models.ForeignKey(
        NhatKyCong, on_delete=models.CASCADE, related_name='adjustments',
    )
    cham_cong = models.ForeignKey(
        ChamCong, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='adjustments',
    )
    nguoi_thuc_hien = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    truong_dieu_chinh = models.CharField('Trường điều chỉnh', max_length=40)
    gia_tri_cu = models.TextField('Giá trị cũ', blank=True)
    gia_tri_moi = models.TextField('Giá trị mới', blank=True)
    ly_do = models.TextField('Lý do')
    ngay_dieu_chinh = models.DateTimeField('Ngày điều chỉnh')

    class Meta:
        db_table = 'Lich_su_dieu_chinh_cong'
        constraints = [
            models.UniqueConstraint(
                fields=['nhat_ky', 'truong_dieu_chinh'],
                name='unique_audit_changed_field',
            ),
        ]

