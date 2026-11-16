from uuid import uuid4

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


def tao_ma_tong_thuong():
    return 'T' + uuid4().hex[:24]


def tao_ma_de_xuat():
    return 'D' + uuid4().hex[:24]


class Thuong(models.Model):
    STATUSES = [('draft', 'Bản nháp'), ('pending', 'Chờ duyệt'),
                ('approved', 'Đã duyệt'), ('rejected', 'Từ chối')]

    ma_thuong = models.CharField(primary_key=True, max_length=25, default=tao_ma_tong_thuong,
                                 editable=False, db_column='Ma_thuong')
    nguoi_dung = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name='bang_thuong', db_column='Ma_nguoi_dung')
    thang = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)], db_column='Thang')
    nam = models.IntegerField(validators=[MinValueValidator(2000), MaxValueValidator(2100)], db_column='Nam')
    thuong_chuyen_can = models.DecimalField(max_digits=12, decimal_places=0, default=0, db_column='Thuong_chuyen_can')
    thuong_tham_nien = models.DecimalField(max_digits=12, decimal_places=0, default=0, db_column='Thuong_tham_nien')
    thuong_khac = models.DecimalField(max_digits=12, decimal_places=0, default=0, db_column='Thuong_khac')
    tong_thuong = models.DecimalField(max_digits=12, decimal_places=0, default=0, db_column='Tong_thuong')
    ly_do_chuyen_can = models.TextField(null=True, blank=True, db_column='Ly_do_chuyen_can')
    ly_do_tham_nien = models.TextField(null=True, blank=True, db_column='Ly_do_tham_nien')
    trang_thai = models.CharField(max_length=30, choices=STATUSES, default='draft', db_column='Trang_thai')
    nguoi_duyet = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.PROTECT, related_name='bang_thuong_da_duyet', db_column='Ma_nguoi_duyet')
    ngay_duyet = models.DateTimeField(null=True, blank=True, db_column='Ngay_duyet')
    ly_do_tu_choi = models.TextField(null=True, blank=True, db_column='Ly_do_tu_choi')

    class Meta:
        db_table = 'Thuong'
        ordering = ['nguoi_dung__employee__ma_ho_so', '-nam', '-thang']
        constraints = [
            models.UniqueConstraint(fields=['nguoi_dung', 'nam', 'thang'], name='thuong_moi_nguoi_mot_ky'),
            models.CheckConstraint(check=Q(thang__gte=1, thang__lte=12, nam__gte=2000, nam__lte=2100), name='thuong_ky_hop_le'),
            models.CheckConstraint(check=Q(thuong_chuyen_can__gte=0, thuong_tham_nien__gte=0, thuong_khac__gte=0,
                tong_thuong__lte=999999999999) & Q(tong_thuong=F('thuong_chuyen_can') + F('thuong_tham_nien') + F('thuong_khac')),
                name='thuong_so_tien_hop_le'),
            models.CheckConstraint(check=Q(trang_thai__in=['draft', 'pending', 'approved', 'rejected']), name='thuong_trang_thai_hop_le'),
            models.CheckConstraint(check=~Q(trang_thai__in=['approved', 'rejected'])
                | Q(nguoi_duyet__isnull=False, ngay_duyet__isnull=False), name='thuong_duyet_du_thong_tin'),
            models.CheckConstraint(check=~Q(trang_thai='rejected')
                | (Q(ly_do_tu_choi__isnull=False) & ~Q(ly_do_tu_choi='')), name='thuong_tu_choi_co_ly_do'),
        ]


class DeXuatThuong(models.Model):
    ma_de_xuat_thuong = models.CharField(primary_key=True, max_length=25, default=tao_ma_de_xuat,
                                        editable=False, db_column='Ma_de_xuat_thuong')
    bang_thuong = models.ForeignKey(Thuong, on_delete=models.PROTECT, related_name='de_xuat', db_column='Ma_thuong')
    ten = models.CharField('Tên thưởng khác', max_length=100, db_column='Ten_thuong')
    so_tien = models.DecimalField('Số tiền', max_digits=12, decimal_places=0, validators=[MinValueValidator(0)], db_column='So_tien')
    ly_do = models.TextField('Lý do', db_column='Ly_do')
    nguoi_de_xuat = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column='Ma_nguoi_de_xuat')
    thoi_gian_de_xuat = models.DateTimeField(default=timezone.now, db_column='Ngay_de_xuat')

    class Meta:
        db_table = 'De_xuat_thuong'
        constraints = [
            models.CheckConstraint(check=Q(so_tien__gte=0, so_tien__lte=999999999999), name='de_xuat_tien_hop_le'),
            models.CheckConstraint(check=~Q(ten='') & ~Q(ly_do=''), name='de_xuat_du_noi_dung'),
        ]
