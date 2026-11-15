from datetime import time
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.db import models


class PayrollPeriod(models.Model):
    thang = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    nam = models.PositiveSmallIntegerField(validators=[MinValueValidator(2000), MaxValueValidator(2100)])
    trang_thai = models.CharField(max_length=10, default='pending',
        choices=[('pending', 'Chờ duyệt'), ('approved', 'Đã duyệt')])
    phien_ban = models.PositiveIntegerField(default=1)
    ds_nhan_vien = models.JSONField(default=list, blank=True)
    nguoi_duyet = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.PROTECT, related_name='approved_attendance_months')
    ngay_duyet = models.DateTimeField(null=True, blank=True)
    can_cu_cong = models.JSONField(default=dict, blank=True, editable=False)
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

    class Meta:
        constraints = [models.UniqueConstraint(fields=['nam', 'thang'], name='unique_salary_month')]
        ordering = ['-nam', '-thang']

    def __str__(self):
        return f'{self.thang:02}/{self.nam}'

    def _gio_ca(self, truong, mac_dinh):
        return time.fromisoformat(self.can_cu_cong.get(truong, mac_dinh))

    def _luu_gio_ca(self, truong, gia_tri):
        self.can_cu_cong = {**self.can_cu_cong, truong: str(gia_tri)}

    gio_bat_dau = property(lambda s: s._gio_ca('gio_bat_dau', '08:00'),
                          lambda s, v: s._luu_gio_ca('gio_bat_dau', v))
    bat_dau_nghi_trua = property(lambda s: s._gio_ca('bat_dau_nghi_trua', '12:00'),
                                lambda s, v: s._luu_gio_ca('bat_dau_nghi_trua', v))
    ket_thuc_nghi_trua = property(lambda s: s._gio_ca('ket_thuc_nghi_trua', '13:00'),
                                 lambda s, v: s._luu_gio_ca('ket_thuc_nghi_trua', v))
    gio_ket_thuc = property(lambda s: s._gio_ca('gio_ket_thuc', '17:00'),
                           lambda s, v: s._luu_gio_ca('gio_ket_thuc', v))
    gio_chuan = property(lambda s: Decimal(s.can_cu_cong.get('gio_chuan', '8')),
                        lambda s, v: s._luu_gio_ca('gio_chuan', v))
    lich_luu_tru = property(lambda s: s.can_cu_cong.get('lich', {}),
                           lambda s, v: setattr(s, 'can_cu_cong', {**s.can_cu_cong, 'lich': v}))

    @property
    def attendance_period(self):
        """Tương thích cách đọc cũ; công và lương dùng chung một tháng."""
        return self

    @property
    def attendance_period_id(self):
        return self.pk

    @property
    def employee_approvals(self):
        from bang_cong.models import ChotBangCong

        return ChotBangCong.objects.filter(tong_hop__ky_cong=self)

    def clean(self):
        if not self.gio_bat_dau < self.bat_dau_nghi_trua < self.ket_thuc_nghi_trua < self.gio_ket_thuc:
            raise ValidationError('Thứ tự giờ làm/nghỉ trưa không hợp lệ.')
        if self.gio_chuan <= 0:
            raise ValidationError('Giờ chuẩn phải lớn hơn 0.')

class Luong(models.Model):
    ma_luong = models.CharField(max_length=20, unique=True, editable=False, db_column='Ma_luong')
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
        ('pending', 'Chờ duyệt'), ('approved', 'Đã duyệt'), ('paid', 'Đã chi trả')], db_column='Trang_thai')
    nguoi_duyet = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='approved_salary_records')
    ngay_duyet = models.DateTimeField(null=True, blank=True)
    ma_nhan_vien = models.CharField(max_length=30)
    ten_nhan_vien = models.CharField(max_length=150)
    ma_phong_ban_luu = models.PositiveBigIntegerField()
    ten_phong_ban = models.CharField(max_length=150)
    luong_co_ban = models.DecimalField(max_digits=18, decimal_places=2, db_column='Luong_co_ban')
    cong_chuan = models.DecimalField(max_digits=10, decimal_places=4)
    cong_huong_luong = models.DecimalField(max_digits=10, decimal_places=4)
    cong_nghi_phep = models.DecimalField(max_digits=10, decimal_places=4)
    so_phut_tre = models.PositiveIntegerField()
    so_gio_tang_ca = models.DecimalField(max_digits=10, decimal_places=4)
    luong_theo_cong = models.DecimalField(max_digits=24, decimal_places=8, db_column='Luong_theo_cong')
    luong_tang_ca = models.DecimalField(max_digits=24, decimal_places=8, default=0, db_column='Luong_tang_ca')
    tong_tien_thuong = models.DecimalField(max_digits=24, decimal_places=8, default=0, db_column='Tong_tien_thuong')
    phu_cap = models.DecimalField(max_digits=24, decimal_places=8)
    tong_bao_hiem = models.DecimalField(max_digits=24, decimal_places=8)
    thue_tncn = models.DecimalField(max_digits=24, decimal_places=8, default=0, db_column='Thue_TNCN')
    tong_khau_tru = models.DecimalField(max_digits=24, decimal_places=8)
    luong_thuc_linh = models.DecimalField(max_digits=18, decimal_places=0, db_column='Luong_thuc_linh')
    chi_tiet = models.JSONField()
    ngay_tinh = models.DateTimeField(auto_now=True)

    khau_tru_di_tre = models.DecimalField(max_digits=12, decimal_places=0, default=0, db_column='Khau_tru_di_tre')
    khau_tru_bhxh = models.DecimalField(max_digits=24, decimal_places=8, default=0, db_column='Khau_tru_BHXH')
    khau_tru_bhyt = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    khau_tru_bhtn = models.DecimalField(max_digits=24, decimal_places=8, default=0)
    khau_tru_khac = models.DecimalField(max_digits=24, decimal_places=8, default=0)

    def clean(self):
        if not self.ky_luong_id or not self.nhan_vien_id:
            return
        ky_cong = self.ky_luong.attendance_period
        if self.tong_hop_id and (
            self.tong_hop.nhan_vien_id, self.tong_hop.ky_cong_id,
            self.tong_hop.nam, self.tong_hop.thang,
        ) != (self.nhan_vien_id, ky_cong.pk, ky_cong.nam, ky_cong.thang):
            raise ValidationError('Tổng hợp công phải thuộc đúng nhân viên và kỳ lương.')
        if self.tong_thuong_id and (
            self.tong_thuong.nhan_vien_id, self.tong_thuong.nam, self.tong_thuong.thang,
        ) != (self.nhan_vien_id, ky_cong.nam, ky_cong.thang):
            raise ValidationError('Tổng thưởng phải thuộc đúng nhân viên và kỳ lương.')

    def save(self, *args, **kwargs):
        # Liên kết được ghi cùng phiếu; việc xem/tính đối chiếu không tạo dữ liệu.
        from django.db import transaction
        from .services.tinh_toan import lien_ket_nguon_luong

        with transaction.atomic(using=kwargs.get('using') or self._state.db):
            self.clean()
            fields = kwargs.get('update_fields')
            if (not self.tong_hop_id or not self.tong_thuong_id or not self.ma_luong
                    or (self.trang_thai == 'pending' and (fields is None or 'chi_tiet' in fields))):
                lien_ket_nguon_luong(self)
            self.clean()
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
