from django.db import models  # Nạp các lớp trường và kiểu model của Django.


class TongHopCong(models.Model):  # Khai báo model ánh xạ tới bảng tổng hợp công theo tháng.
    """Tổng hợp một nhân viên/tháng, làm căn cứ tính lương qua services."""
    # Khóa chính tự tăng của bản tổng hợp tháng.
    id = models.BigAutoField(  # Trường khóa chính dạng số nguyên lớn, tự tăng.
        primary_key=True,  # Đánh dấu đây là khóa chính của mỗi bản ghi.
    )

    # Tháng/năm lấy trực tiếp từ dữ liệu tổng hợp và lịch chấm công.
    # Nhân viên được tổng hợp; tên truy cập ngược mặc định là nhanvien.tonghopcong_set.all().
    nhan_vien = models.ForeignKey(  # Liên kết bản tổng hợp này với một nhân viên.
        'employees.NhanVien',  # Model đích nằm trong ứng dụng employees.
        on_delete=models.CASCADE,  # Xóa tổng hợp khi nhân viên liên kết bị xóa.
    )
    # Tháng/năm của kết quả tổng hợp, phải khớp kỳ liên kết.
    thang = models.PositiveSmallIntegerField()  # Tháng tổng hợp; chỉ nhận số nguyên không âm cỡ nhỏ.
    nam = models.PositiveSmallIntegerField()  # Năm tổng hợp; chỉ nhận số nguyên không âm cỡ nhỏ.
    # Tổng công chuẩn của lịch tháng, dùng làm căn cứ tính lương theo công.
    cong_chuan = models.DecimalField(max_digits=14, decimal_places=4, default=0)  # Công chuẩn; tối đa 14 chữ số, trong đó 4 chữ số thập phân.
    # Tổng công thực tế làm được, có thể gồm công lẻ.
    cong_thuc_te = models.DecimalField(max_digits=14, decimal_places=4, default=0)  # Công thực tế, cho phép lưu phần lẻ; mặc định bằng 0.
    # Tổng công nghỉ hưởng lương được ghi nhận.
    cong_nghi_co_luong = models.DecimalField(max_digits=14, decimal_places=4, default=0)  # Số công nghỉ có hưởng lương; mặc định bằng 0.
    # Số ngày được ghi nhận nghỉ không phép.
    so_ngay_khong_phep = models.PositiveIntegerField(default=0)  # Số ngày nghỉ không phép; chỉ nhận số nguyên không âm.
    # Tổng công hưởng lương của nhân viên trong tháng.
    tong_cong = models.DecimalField(max_digits=14, decimal_places=4, default=0)  # Tổng công hưởng lương; mặc định bằng 0.
    # Tổng số giờ tăng ca trong tháng.
    tong_gio_tang_ca = models.DecimalField(
        'Tổng giờ tăng ca',  # Nhãn hiển thị thân thiện của trường.
        max_digits=14,  # Tổng số chữ số tối đa của giá trị.
        decimal_places=4,  # Số chữ số được lưu sau dấu thập phân.
        default=0,  # Giá trị mặc định khi chưa có dữ liệu tăng ca.
    )
    # Số lần đi trễ và tổng số phút đi trễ của tháng.
    so_lan_tre = models.PositiveIntegerField(default=0)  # Số lần đi trễ; mặc định bằng 0.
    so_phut_tre = models.PositiveIntegerField(default=0)  # Tổng phút đi trễ; mặc định bằng 0.
    # Trạng thái tổng hợp, mặc định chờ chốt; không phải trạng thái công ngày.
    trang_thai = models.CharField(  # Trường văn bản lưu trạng thái chốt của bản tổng hợp.
        max_length=12,  # Giới hạn độ dài chuỗi trạng thái tối đa 12 ký tự.
        default='pending',  # Trạng thái mặc định là đang chờ chốt.
        choices=[
            ('pending', 'Chờ chốt'),  # Mã lưu pending, nhãn hiển thị Chờ chốt.
            ('approved', 'Đã chốt'),  # Mã lưu approved, nhãn hiển thị Đã chốt.
            ('empty', 'Chưa có dữ liệu'),  # Mã lưu empty, nhãn hiển thị Chưa có dữ liệu.
        ],
    )
    class Meta:  # Khai báo tùy chọn áp dụng cho toàn bộ model.
        # Tên bảng tổng hợp trong database.
        db_table = 'Tong_hop_cong'  # Chỉ định tên bảng trong cơ sở dữ liệu.
        constraints = [  # Danh sách các ràng buộc dữ liệu ở cấp cơ sở dữ liệu.
            # Không tạo hai tổng hợp của cùng nhân viên trong cùng tháng/năm.
            models.UniqueConstraint(  # Bảo đảm mỗi nhân viên chỉ có một bản tổng hợp cho mỗi tháng/năm.
                fields=['nhan_vien', 'nam', 'thang'],  # Bộ trường kết hợp phải có giá trị duy nhất.
                name='unique_employee_month_summary',  # Tên ràng buộc dùng trong cơ sở dữ liệu.
            ),
        ]
