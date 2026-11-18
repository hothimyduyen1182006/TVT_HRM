from django.conf import settings  # Lấy cấu hình tài khoản người dùng đang dùng trong dự án.
from django.db import models  # Dùng các kiểu model và trường dữ liệu của Django.


class ChotBangCong(models.Model):  # Khai báo bảng lưu thông tin duyệt/chốt công.
    """Một bản chốt cho mỗi nhân viên/tháng, liên kết đúng bản tổng hợp."""
    # Khóa chính tự tăng của bản chốt.
    id = models.BigAutoField(  # Tạo mã số tự tăng riêng cho mỗi lần chốt.
        primary_key=True,  # Đánh dấu trường này là khóa chính của bảng.
    )
    # Một tổng hợp có tối đa một bản chốt; mặc định truy cập ngược là tong_hop.chotbangcong.
    tong_hop = models.OneToOneField(  # Nối bản chốt này với một bản tổng hợp công.
        'TongHopCong',  # Model tổng hợp công được liên kết trong cùng ứng dụng.
        on_delete=models.PROTECT,  # Không cho xóa bản tổng hợp khi bản chốt này còn tham chiếu.
    )
    # Tài khoản thực hiện duyệt; cho phép trống để hỗ trợ dữ liệu lịch sử.
    nguoi_duyet = models.ForeignKey(  # Lưu tài khoản đã thực hiện chốt công.
        settings.AUTH_USER_MODEL,  # Trỏ đến model tài khoản được cấu hình cho dự án.
        on_delete=models.PROTECT,  # Không cho xóa tài khoản nếu tài khoản còn được ghi là người chốt.
    )
    # Tự ghi thời điểm tạo lần đầu; không tự cập nhật ở những lần sửa sau.
    ngay_duyet = models.DateTimeField(  # Lưu ngày và giờ bản chốt được tạo.
        auto_now_add=True,  # Django tự ghi thời điểm tạo lần đầu, không đổi khi sửa bản ghi.
    )

    class Meta:  # Chứa các thiết lập áp dụng cho model, không phải các cột dữ liệu.
        # Tên bảng chốt công trong database.
        db_table = 'Chot_bang_cong'  # Dùng tên bảng này trong cơ sở dữ liệu.
