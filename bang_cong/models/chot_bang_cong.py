from django.conf import settings
from django.db import models


class ChotBangCong(models.Model):
    """Một bản chốt cho mỗi nhân viên/tháng, liên kết đúng bản tổng hợp."""
    ma_chot = models.BigAutoField(
        primary_key=True,
    )
    tong_hop = models.OneToOneField(
        'TongHopCong',
        on_delete=models.PROTECT,
    )
    # Ghi nhận người chốt và thời điểm chốt.
    nguoi_duyet = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
    )
    ngay_duyet = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = 'Chot_bang_cong'
