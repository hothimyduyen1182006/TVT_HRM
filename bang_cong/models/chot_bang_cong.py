from django.conf import settings
from django.db import models


class ChotBangCong(models.Model):
    """Một bản chốt cho mỗi nhân viên/tháng, liên kết đúng bản tổng hợp."""
    # Khóa chính tự tăng của bản chốt.
    id = models.BigAutoField(primary_key=True, db_column='Ma_chot')
    # Một tổng hợp có tối đa một bản chốt; tổng_hợp.approval đọc bản chốt.
    tong_hop = models.OneToOneField(
        'TongHopCong', on_delete=models.PROTECT,
        related_name='approval', verbose_name='Bản tổng hợp công',
        db_column='Ma_tong_hop',
    )
    # Tài khoản thực hiện duyệt; cho phép trống để hỗ trợ dữ liệu lịch sử.
    nguoi_duyet = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        db_column='Ma_nguoi_chot',
    )
    # Tự ghi thời điểm tạo lần đầu; không tự cập nhật ở những lần sửa sau.
    ngay_duyet = models.DateTimeField(auto_now_add=True, db_column='Ngay_chot')

    class Meta:
        # Tên bảng chốt công trong database.
        db_table = 'Chot_bang_cong'
