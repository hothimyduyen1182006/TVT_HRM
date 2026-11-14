from django.conf import settings
from django.db import models


class PayrollPeriod(models.Model):
    attendance_period = models.OneToOneField('attendance.KyCong', on_delete=models.PROTECT)
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

class Luong(models.Model):
    ma_luong = models.CharField(max_length=20, unique=True, editable=False)
    tong_hop = models.OneToOneField(
        'attendance.TongHopCong', on_delete=models.PROTECT,
        related_name='phieu_luong', db_column='Ma_tong_hop',
    )
    tong_thuong = models.OneToOneField(
        'bonuses.TongThuong', on_delete=models.PROTECT,
        related_name='phieu_luong', db_column='Ma_thuong',
    )
    ky_luong = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name='records')
    nhan_vien = models.ForeignKey('employees.Employee', on_delete=models.PROTECT)
    trang_thai = models.CharField(max_length=10, default='pending', choices=[
        ('pending', 'Chờ duyệt'), ('approved', 'Đã duyệt'), ('paid', 'Đã chi trả')])
    nguoi_duyet = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='approved_salary_records')
    ngay_duyet = models.DateTimeField(null=True, blank=True)
    ma_nhan_vien = models.CharField(max_length=30)
    ten_nhan_vien = models.CharField(max_length=150)
    ma_phong_ban_luu = models.PositiveBigIntegerField()
    ten_phong_ban = models.CharField(max_length=150)
    luong_co_ban = models.DecimalField(max_digits=18, decimal_places=2)
    cong_chuan = models.DecimalField(max_digits=10, decimal_places=4)
    cong_huong_luong = models.DecimalField(max_digits=10, decimal_places=4)
    cong_nghi_phep = models.DecimalField(max_digits=10, decimal_places=4)
    so_phut_tre = models.PositiveIntegerField()
    so_gio_tang_ca = models.DecimalField(max_digits=10, decimal_places=4)
    luong_theo_cong = models.DecimalField(max_digits=24, decimal_places=8)
    luong_tang_ca = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    tong_tien_thuong = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    phu_cap = models.DecimalField(max_digits=24, decimal_places=8)
    tong_bao_hiem = models.DecimalField(max_digits=24, decimal_places=8)
    thue_tncn = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    tong_khau_tru = models.DecimalField(max_digits=24, decimal_places=8)
    luong_thuc_linh = models.DecimalField(max_digits=18, decimal_places=0)
    chi_tiet = models.JSONField()
    ngay_tinh = models.DateTimeField(auto_now=True)

    khau_tru_di_tre = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    khau_tru_bhxh = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    khau_tru_bhyt = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    khau_tru_bhtn = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    khau_tru_khac = models.DecimalField(max_digits=24, decimal_places=8, default=0)

    def save(self, *args, **kwargs):
        # Liên kết được ghi cùng phiếu; việc xem/tính đối chiếu không tạo dữ liệu.
        from django.db import transaction
        from .services.tinh_toan import lien_ket_nguon_luong

        with transaction.atomic(using=kwargs.get('using') or self._state.db):
            fields = kwargs.get('update_fields')
            if (not self.tong_hop_id or not self.tong_thuong_id or not self.ma_luong
                    or (self.trang_thai == 'pending' and (fields is None or 'chi_tiet' in fields))):
                lien_ket_nguon_luong(self)
            super().save(*args, **kwargs)

    class Meta:
        db_table = 'Luong'
        constraints = [models.UniqueConstraint(fields=['ky_luong', 'nhan_vien'], name='unique_payroll_record')]
        ordering = ['ma_nhan_vien']


class PayrollAuditLog(models.Model):
    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=30)
    reason = models.TextField()
    snapshot = models.JSONField(default=list)
