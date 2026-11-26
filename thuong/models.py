from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Thuong(models.Model):
    TRANG_THAI = [('ban_nhap', 'Bản nháp'), ('cho_duyet', 'Chờ duyệt'),
                ('da_duyet', 'Đã duyệt'), ('tu_choi', 'Từ chối')]

    ma_thuong = models.CharField(primary_key=True, max_length=25, editable=False)
    nguoi_dung = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name='bang_thuong', db_column='nguoi_dung')
    thang = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    nam = models.IntegerField(validators=[MinValueValidator(2000), MaxValueValidator(2100)])
    thuong_chuyen_can = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    thuong_tham_nien = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    thuong_khac = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    tong_thuong = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    ly_do_chuyen_can = models.TextField(null=True, blank=True)
    ly_do_tham_nien = models.TextField(null=True, blank=True)
    trang_thai = models.CharField(max_length=30, choices=TRANG_THAI, default='ban_nhap')
    nguoi_duyet = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.PROTECT, related_name='bang_thuong_da_duyet', db_column='nguoi_duyet')
    ngay_duyet = models.DateTimeField(null=True, blank=True)
    ly_do_tu_choi = models.TextField(null=True, blank=True)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        if not self.ma_thuong:
            self.ma_thuong = f'MT{self.nam - 2000:02d}{self.thang:02d}-{self.nguoi_dung_id:03d}'
            force_insert = True
        super().save(force_insert, force_update, using, update_fields)

    class Meta:
        db_table = 'Thuong'
        ordering = ['nguoi_dung__employee__ma_ho_so', '-nam', '-thang']
        constraints = [
            models.UniqueConstraint(fields=['nguoi_dung', 'nam', 'thang'], name='thuong_moi_nguoi_mot_ky'),
            models.CheckConstraint(check=Q(thang__gte=1, thang__lte=12, nam__gte=2000, nam__lte=2100), name='thuong_ky_hop_le'),
            models.CheckConstraint(check=Q(thuong_chuyen_can__gte=0, thuong_tham_nien__gte=0, thuong_khac__gte=0,
                tong_thuong__lte=999999999999) & Q(tong_thuong=F('thuong_chuyen_can') + F('thuong_tham_nien') + F('thuong_khac')),
                name='thuong_so_tien_hop_le'),
            models.CheckConstraint(check=Q(trang_thai__in=['ban_nhap', 'cho_duyet', 'da_duyet', 'tu_choi']), name='thuong_trang_thai_hop_le'),
            models.CheckConstraint(check=~Q(trang_thai__in=['da_duyet', 'tu_choi'])
                | Q(nguoi_duyet__isnull=False, ngay_duyet__isnull=False), name='thuong_duyet_du_thong_tin'),
            models.CheckConstraint(check=~Q(trang_thai='tu_choi')
                | (Q(ly_do_tu_choi__isnull=False) & ~Q(ly_do_tu_choi='')), name='thuong_tu_choi_co_ly_do'),
        ]


class DeXuatThuong(models.Model):
    ma_de_xuat_thuong = models.BigAutoField(primary_key=True)
    bang_thuong = models.ForeignKey(Thuong, on_delete=models.PROTECT, related_name='de_xuat', db_column='bang_thuong')
    ten = models.CharField('Tên thưởng khác', max_length=100)
    so_tien = models.DecimalField('Số tiền', max_digits=12, decimal_places=0, validators=[MinValueValidator(0)])
    ly_do = models.TextField('Lý do')
    nguoi_de_xuat = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column='nguoi_de_xuat')
    thoi_gian_de_xuat = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'De_xuat_thuong'
        constraints = [
            models.CheckConstraint(check=Q(so_tien__gte=0, so_tien__lte=999999999999), name='de_xuat_tien_hop_le'),
            models.CheckConstraint(check=~Q(ten='') & ~Q(ly_do=''), name='de_xuat_du_noi_dung'),
        ]
