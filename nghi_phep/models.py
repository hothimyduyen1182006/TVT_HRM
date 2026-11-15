
from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


SO_NGAY_PHEP_NAM = 12


def tinh_ngay_phep_da_dung(nhan_vien, nam, bo_qua_ma_don=None):
    dau_nam = date(nam, 1, 1)
    cuoi_nam = date(nam, 12, 31)

    cac_don = DonNghiPhep.objects.filter(
        nhan_vien=nhan_vien,
        loai_nghi='phep_nam',
        trang_thai__in=['cho_duyet', 'da_duyet'],
        ngay_bat_dau__lte=cuoi_nam,
        ngay_ket_thuc__gte=dau_nam,
    )
    if bo_qua_ma_don is not None:
        cac_don = cac_don.exclude(pk=bo_qua_ma_don)

    cac_ngay_da_dung = set()

    for don in cac_don.only('ngay_bat_dau', 'ngay_ket_thuc'):
        ngay_dau = max(don.ngay_bat_dau, dau_nam)
        ngay_cuoi = min(don.ngay_ket_thuc, cuoi_nam)

        for so_ngay_lech in range((ngay_cuoi - ngay_dau).days + 1):
            cac_ngay_da_dung.add(ngay_dau + timedelta(days=so_ngay_lech))

    return len(cac_ngay_da_dung)


class DonNghiPhep(models.Model):
    LOAI_NGHI = [
        ('phep_nam', 'Nghỉ theo quỹ phép'),
        ('luong_dac_biet', 'Nghỉ hưởng lương đặc biệt'),
        ('khong_luong', 'Nghỉ không lương'),
    ]

    CAC_TRANG_THAI = [
        ('cho_duyet', 'Đang chờ'),
        ('da_duyet', 'Đã duyệt'),
        ('tu_choi', 'Từ chối'),
        ('da_huy', 'Đã hủy'),
    ]

    ma_don = models.BigAutoField(primary_key=True)

    nhan_vien = models.ForeignKey(
        'employees.Employee',
        on_delete=models.PROTECT,
        related_name='don_nghi_phep',
        db_column='Ma_nguoi_dung',
    )

    ngay_bat_dau = models.DateField('Từ ngày')
    ngay_ket_thuc = models.DateField('Đến ngày')

    loai_nghi = models.CharField(
        'Loại nghỉ',
        max_length=20,
        choices=LOAI_NGHI,
        default='phep_nam',
    )

    ly_do = models.CharField('Lý do', max_length=255)

    tep_dinh_kem = models.FileField(
        'Ảnh minh chứng',
        upload_to='leave_evidence/%Y/%m/',
        blank=True,
        null=True,
    )

    trang_thai = models.CharField(
        'Trạng thái',
        max_length=12,
        choices=CAC_TRANG_THAI,
        default='cho_duyet',
    )

    ghi_chu_duyet = models.TextField(
        'Lý do từ chối',
        blank=True,
    )

    ngay_tao = models.DateTimeField(auto_now_add=True)

    nguoi_duyet = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='don_nghi_phep_da_duyet',
    )

    ngay_duyet = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ['-ngay_tao']

    @property
    def so_ngay_nghi(self):
        return (self.ngay_ket_thuc - self.ngay_bat_dau).days + 1

    @property
    def huong_luong(self):
        return self.loai_nghi in ('phep_nam', 'luong_dac_biet')

    def clean(self):
        loi = {}
        if self.ngay_bat_dau and self.ngay_ket_thuc:
            if self.ngay_ket_thuc < self.ngay_bat_dau:
                raise ValidationError({
                    'ngay_ket_thuc': 'Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.'
                })

            if self.nhan_vien_id and self.trang_thai in ('cho_duyet', 'da_duyet'):
                don_trung = DonNghiPhep.objects.filter(
                    nhan_vien_id=self.nhan_vien_id,
                    trang_thai__in=('cho_duyet', 'da_duyet'),
                    ngay_bat_dau__lte=self.ngay_ket_thuc,
                    ngay_ket_thuc__gte=self.ngay_bat_dau,
                ).exclude(pk=self.pk)
                if don_trung.exists():
                    loi['ngay_bat_dau'] = 'Khoảng thời gian nghỉ bị trùng với một đơn khác.'

            if self.nhan_vien_id and self.ngay_bat_dau < self.nhan_vien.hire_date:
                loi['ngay_bat_dau'] = 'Ngày nghỉ không được trước ngày vào làm.'

            if self.nhan_vien_id and self.loai_nghi == 'phep_nam':
                for nam in range(self.ngay_bat_dau.year, self.ngay_ket_thuc.year + 1):
                    dau_nam = max(self.ngay_bat_dau, date(nam, 1, 1))
                    cuoi_nam = min(self.ngay_ket_thuc, date(nam, 12, 31))
                    so_ngay_yeu_cau = (cuoi_nam - dau_nam).days + 1
                    da_dung = tinh_ngay_phep_da_dung(self.nhan_vien, nam, self.pk)
                    if da_dung + so_ngay_yeu_cau > SO_NGAY_PHEP_NAM:
                        con_lai = max(0, SO_NGAY_PHEP_NAM - da_dung)
                        loi['loai_nghi'] = f'Năm {nam} chỉ còn {con_lai} ngày phép năm.'
                        break

        if loi:
            raise ValidationError(loi)

    def huy(self):
        if self.trang_thai != 'cho_duyet':
            raise ValidationError('Chỉ được hủy đơn đang chờ duyệt.')

        self.trang_thai = 'da_huy'
        self.save(update_fields=['trang_thai'])

    def __str__(self):
        return f'Đơn nghỉ phép #{self.ma_don} - {self.nhan_vien}'


class NgayNghi(models.Model):
    don_nghi_phep = models.ForeignKey(
        DonNghiPhep,
        on_delete=models.PROTECT,
        related_name='cac_ngay_nghi',
    )

    ngay = models.DateField('Ngày nghỉ')

    class Meta:
        ordering = ['-ngay']
        constraints = [
            models.UniqueConstraint(
                fields=['don_nghi_phep', 'ngay'],
                name='unique_leave_request_day',
            ),
        ]

    @property
    def nhan_vien(self):
        return self.don_nghi_phep.nhan_vien

    @property
    def huong_luong(self):
        return self.don_nghi_phep.huong_luong

    def __str__(self):
        return f'{self.nhan_vien} - {self.ngay}'
