from django.core.exceptions import ValidationError
from django.db import models


class Luong(models.Model):
    ma_luong = models.BigAutoField(primary_key=True)
    tong_hop = models.OneToOneField(
        'attendance.TongHopCong', on_delete=models.PROTECT,
    )
    tong_thuong = models.OneToOneField(
        'bonuses.Thuong', on_delete=models.PROTECT,
        null=True, blank=True,
    )
    luong_co_ban = models.DecimalField(max_digits=12, decimal_places=0)
    luong_theo_cong = models.DecimalField(max_digits=12, decimal_places=0)
    luong_tang_ca = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    phu_cap = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    tong_tien_thuong = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    khau_tru_di_tre = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    khau_tru_bhxh = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    khau_tru_khac = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    thue_tncn = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    luong_thuc_linh = models.DecimalField(max_digits=12, decimal_places=0)
    trang_thai = models.CharField(
        max_length=20,
        default='Cho_duyet',
        choices=[
            ('Cho_duyet', 'Chờ HR kiểm tra'),
            ('Cho_giam_doc_duyet', 'Chờ Giám đốc ký duyệt'),
            ('Da_duyet', 'Đã duyệt'),
        ],
    )

    class Meta:
        db_table = 'Luong'
        ordering = ['tong_hop__nhan_vien__ma_ho_so']

    def clean(self):
        super().clean()
        if not self.tong_hop_id:
            raise ValidationError('Phiếu lương cần liên kết tổng hợp công.')
        if self.tong_thuong_id is None:
            return
        summary, bonus = self.tong_hop, self.tong_thuong
        if (summary.nhan_vien_id, summary.nam, summary.thang) != (bonus.nguoi_dung.employee.pk, bonus.nam, bonus.thang):
            raise ValidationError('Công và thưởng phải thuộc cùng nhân viên và tháng/năm.')

    def save(self, *args, **kwargs):
        """Kiểm tra dữ liệu phiếu lương trước khi lưu."""
        self.full_clean()
        return super().save(*args, **kwargs)
