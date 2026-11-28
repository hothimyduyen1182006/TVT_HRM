from django.db import models


class TongHopCong(models.Model):
    """Tổng hợp một nhân viên/tháng, làm căn cứ tính lương qua services."""
    ma_tong_hop = models.BigAutoField(
        primary_key=True,
    )

    nhan_vien = models.ForeignKey(
        'employees.NhanVien',
        on_delete=models.CASCADE,
    )
    thang = models.PositiveSmallIntegerField()
    nam = models.PositiveSmallIntegerField()

    # Số công và thời gian làm việc trong kỳ tổng hợp.
    cong_chuan = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    cong_thuc_te = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    cong_nghi_co_luong = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    so_ngay_khong_phep = models.PositiveIntegerField(default=0)
    tong_cong = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    tong_gio_tang_ca = models.DecimalField(
        'Tổng giờ tăng ca',
        max_digits=14,
        decimal_places=4,
        default=0,
    )
    so_lan_tre = models.PositiveIntegerField(default=0)
    so_phut_tre = models.PositiveIntegerField(default=0)

    # Trạng thái chốt bảng công tháng.
    trang_thai = models.CharField(
        max_length=12,
        default='pending',
        choices=[
            ('pending', 'Chờ chốt'),
            ('approved', 'Đã chốt'),
            ('empty', 'Chưa có dữ liệu'),
        ],
    )

    def __str__(self):
        return f'{self.nhan_vien} · {self.thang:02d}/{self.nam}'

    class Meta:
        db_table = 'Tong_hop_cong'
        # Mỗi nhân viên chỉ có một bản tổng hợp trong mỗi tháng.
        constraints = [
            models.UniqueConstraint(
                fields=['nhan_vien', 'nam', 'thang'],
                name='tong_hop_duy_nhat_nhan_vien_thang',
            ),
        ]
