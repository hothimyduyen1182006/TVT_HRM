"""Dữ liệu công ngày, tổng hợp tháng và chốt công."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


class ChamCong(models.Model):
    """Giờ vào/ra và kết quả tính công của một nhân viên trong một ngày."""
    id = models.BigAutoField(primary_key=True)
    nhan_vien = models.ForeignKey('employees.NhanVien', on_delete=models.PROTECT)
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

    # Kết quả tính giờ làm, đi trễ và tăng ca.
    so_gio_lam = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    so_phut_tre = models.PositiveIntegerField(default=0)
    so_gio_tang_ca = models.DecimalField(
        'Giờ tăng ca',
        max_digits=12, decimal_places=4, default=0,
    )


    class Meta:
        db_table = 'Cham_cong'
        ordering = ['-ngay', 'nhan_vien__ma_ho_so']
        # Mỗi nhân viên có một bản công mỗi ngày. Khi đủ hai mốc giờ, giờ ra phải sau giờ vào.
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

    # Kiểm tra giờ chấm công theo trạng thái công ngày.
    def clean(self):
        if self.gio_vao and self.gio_ra and self.gio_ra <= self.gio_vao:
            raise ValidationError('Giờ ra phải sau giờ vào.')

        if self.trang_thai == 'present' and not (self.gio_vao and self.gio_ra):
            raise ValidationError('Có mặt cần đủ giờ vào và ra.')

        if self.trang_thai in ('leave', 'absent') and (self.gio_vao or self.gio_ra):
            raise ValidationError('Nghỉ cả ngày không được có giờ làm.')

    # Đọc công thực tế và công nghỉ có lương từ kết quả tính công ngày.
    @property
    def cong_thuc_te(self):
        return self._cong_ngay()['actual']

    @property
    def cong_nghi_co_luong(self):
        return self._cong_ngay()['leave']

    # Tính và dùng lại kết quả công ngày trên cùng bản ghi.
    def _cong_ngay(self):
        from bang_cong.services.cham_cong_service import ket_qua_cong_ngay

        if '_ket_qua_cong' not in self.__dict__:
            self._ket_qua_cong = ket_qua_cong_ngay(self)
        return self._ket_qua_cong

    @property
    def tong_cong(self):
        """Giá trị suy ra, không lưu thêm một cột trùng hai thành phần."""
        return (Decimal(self.cong_thuc_te) + Decimal(self.cong_nghi_co_luong)).quantize(Decimal('0.0001'))

    @property
    def gio_tang_ca(self):
        """Tên tương thích cho giao diện/lịch sử; dùng cùng giờ OT đã lưu."""
        return Decimal(self.so_gio_tang_ca).quantize(Decimal('0.0001'))
