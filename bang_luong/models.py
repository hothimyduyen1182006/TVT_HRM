from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import models

from bang_cong.thang_lich import thang_lich

class Luong(models.Model):
    ma_luong = models.CharField(max_length=20, primary_key=True, editable=False, db_column='Ma_luong')
    tong_hop = models.OneToOneField(
        'attendance.TongHopCong', on_delete=models.PROTECT,
        related_name='phieu_luong', db_column='Ma_tong_hop',
    )
    tong_thuong = models.OneToOneField(
        'bonuses.Thuong', on_delete=models.PROTECT,
        related_name='phieu_luong', db_column='Ma_thuong',
    )
    luong_co_ban = models.DecimalField(max_digits=12, decimal_places=0, db_column='Luong_co_ban')
    luong_theo_cong = models.DecimalField(max_digits=12, decimal_places=0, db_column='Luong_theo_cong')
    luong_tang_ca = models.DecimalField(max_digits=12, decimal_places=0, default=0, db_column='Luong_tang_ca')
    tong_tien_thuong = models.DecimalField(max_digits=12, decimal_places=0, default=0, db_column='Tong_tien_thuong')
    khau_tru_di_tre = models.DecimalField(max_digits=12, decimal_places=0, default=0, db_column='Khau_tru_di_tre')
    khau_tru_bhxh = models.DecimalField(max_digits=12, decimal_places=0, default=0, db_column='Khau_tru_BHXH')
    thue_tncn = models.DecimalField(max_digits=12, decimal_places=0, default=0, db_column='Thue_TNCN')
    luong_thuc_linh = models.DecimalField(max_digits=12, decimal_places=0, db_column='Luong_thuc_linh')
    trang_thai = models.CharField(max_length=20, default='pending', choices=[
        ('pending', 'Chờ HR kiểm tra'), ('submitted', 'Chờ Giám đốc ký duyệt'),
        ('approved', 'Đã duyệt'), ('paid', 'Đã chi trả'),
    ], db_column='Trang_thai')

    class Meta:
        db_table = 'Luong'
        constraints = [models.CheckConstraint(
            check=models.Q(trang_thai__in=['pending', 'submitted', 'approved', 'paid']),
            name='valid_salary_status',
        )]
        ordering = ['tong_hop__nhan_vien__ma_ho_so']

    @property
    def nhan_vien(self):
        return self.tong_hop.nhan_vien

    @property
    def nhan_vien_id(self):
        return self.tong_hop.nhan_vien_id

    @property
    def ma_nhan_vien(self):
        return self.nhan_vien.ma_ho_so

    @property
    def ten_nhan_vien(self):
        return self.nhan_vien.ho_va_ten

    @property
    def ten_phong_ban(self):
        return self.nhan_vien.phong_ban.ten_phong_ban

    @property
    def ma_phong_ban_luu(self):
        return self.nhan_vien.phong_ban_id

    @property
    def ngay_tinh(self):
        return None

    @property
    def cong_chuan(self):
        return self.tong_hop.cong_chuan

    @property
    def cong_huong_luong(self):
        return self.tong_hop.tong_cong

    @property
    def cong_nghi_phep(self):
        return self.tong_hop.cong_nghi_co_luong

    @property
    def so_phut_tre(self):
        return self.tong_hop.so_phut_tre

    @property
    def so_gio_tang_ca(self):
        from decimal import Decimal
        breakdown = self.chi_tiet if isinstance(self.chi_tiet, dict) else {}
        overtime = breakdown.get('ot')
        if not isinstance(overtime, list):
            overtime = breakdown.get('source_data', {}).get('overtime', [])
        return sum((Decimal(str(item.get('hours', 0))) for item in overtime), Decimal(0))

    @property
    def phu_cap(self):
        return 0

    @property
    def tong_bao_hiem(self):
        return self.khau_tru_bhxh

    @property
    def tong_khau_tru(self):
        return self.khau_tru_di_tre + self.khau_tru_bhxh + self.thue_tncn

    @property
    def khau_tru_bhyt(self):
        return 0

    @property
    def khau_tru_bhtn(self):
        return 0

    @property
    def khau_tru_khac(self):
        return 0

    @property
    def chi_tiet(self):
        from thuong.views import cac_khoan_thuong_tinh_luong
        bonuses = (cac_khoan_thuong_tinh_luong(self.nhan_vien_id, self.tong_hop.nam, self.tong_hop.thang)
                   if self.tong_thuong_id else [])
        return {
            'bonuses': bonuses,
            'insurance': {'BHXH': str(self.khau_tru_bhxh)},
            'ot': [],
            'source_data': {'overtime_policy': 'automatic-checkout-1700-v1'},
        }

    def clean(self):
        if not self.tong_hop_id or not self.tong_thuong_id:
            return
        summary, bonus = self.tong_hop, self.tong_thuong
        if (summary.nhan_vien_id, summary.nam, summary.thang) != (bonus.nguoi_dung.employee.pk, bonus.nam, bonus.thang):
            raise ValidationError('Công và thưởng phải thuộc cùng nhân viên và tháng/năm.')

    def save(self, *args, **kwargs):
        if not self.ma_luong:
            summary = self.tong_hop
            value = f'L{summary.nam}{summary.thang:02}-{summary.nhan_vien_id}'
            self.ma_luong = value if len(value) <= 20 else 'L' + uuid4().hex[:19]
        self.clean()
        return super().save(*args, **kwargs)
