from django.core.exceptions import ValidationError
from django.db import models


class Luong(models.Model):
    CHO_DUYET = 'Cho_duyet'
    CHO_GIAM_DOC_DUYET = 'Cho_giam_doc_duyet'
    DA_DUYET = 'Da_duyet'
    DA_CHI_TRA = 'Da_chi_tra'
    TRANG_THAI = [
        (CHO_DUYET, 'Chờ duyệt'),
        (CHO_GIAM_DOC_DUYET, 'Chờ Giám đốc ký'),
        (DA_DUYET, 'Đã duyệt'),
        (DA_CHI_TRA, 'Đã chi trả'),
    ]

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
    phu_cap = models.DecimalField(max_digits=12, decimal_places=0, default=0, db_column='Phu_cap')
    tong_tien_thuong = models.DecimalField(max_digits=12, decimal_places=0, default=0, db_column='Tong_tien_thuong')
    khau_tru_di_tre = models.DecimalField(max_digits=12, decimal_places=0, default=0, db_column='Khau_tru_di_tre')
    khau_tru_bhxh = models.DecimalField(max_digits=12, decimal_places=0, default=0, db_column='Khau_tru_BHXH')
    khau_tru_bhyt = models.DecimalField(max_digits=12, decimal_places=0, default=0, db_column='Khau_tru_BHYT')
    khau_tru_bhtn = models.DecimalField(max_digits=12, decimal_places=0, default=0, db_column='Khau_tru_BHTN')
    khau_tru_khac = models.DecimalField(max_digits=12, decimal_places=0, default=0, db_column='Khau_tru_khac')
    thue_tncn = models.DecimalField(max_digits=12, decimal_places=0, default=0, db_column='Thue_TNCN')
    luong_thuc_linh = models.DecimalField(max_digits=12, decimal_places=0, db_column='Luong_thuc_linh')
    trang_thai = models.CharField(
        max_length=20, default=CHO_DUYET, choices=TRANG_THAI, db_column='Trang_thai',
    )

    class Meta:
        db_table = 'Luong'
        constraints = [models.CheckConstraint(
            check=models.Q(trang_thai__in=[
                'Cho_duyet', 'Cho_giam_doc_duyet', 'Da_duyet', 'Da_chi_tra',
            ]),
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
        return self.tong_hop.tong_gio_tang_ca

    @property
    def tong_khau_tru(self):
        # Đi trễ đã làm giảm công hưởng lương; không tính thêm khoản trừ riêng.
        return (self.khau_tru_bhxh + self.khau_tru_bhyt + self.khau_tru_bhtn
                + self.thue_tncn + self.khau_tru_khac)

    @property
    def tong_thu_nhap(self):
        return self.luong_theo_cong + self.luong_tang_ca + self.phu_cap + self.tong_tien_thuong

    def clean(self):
        super().clean()
        if not self.tong_hop_id or not self.tong_thuong_id:
            raise ValidationError('Phiếu lương cần liên kết tổng hợp công và bảng thưởng.')
        summary, bonus = self.tong_hop, self.tong_thuong
        if (summary.nhan_vien_id, summary.nam, summary.thang) != (bonus.nguoi_dung.employee.pk, bonus.nam, bonus.thang):
            raise ValidationError('Công và thưởng phải thuộc cùng nhân viên và tháng/năm.')

    def save(self, *args, **kwargs):
        if not self.ma_luong:
            summary = self.tong_hop
            value = f'L{summary.nam}{summary.thang:02}-{summary.nhan_vien_id}'
            if len(value) > 20:
                raise ValidationError('Không thể tạo mã lương trong giới hạn 20 ký tự.')
            self.ma_luong = value
        self.full_clean()
        return super().save(*args, **kwargs)
