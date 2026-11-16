from django.db import models


class TongHopCong(models.Model):
    """Tổng hợp một nhân viên/tháng, làm căn cứ tính lương qua services."""
    # Khóa chính tự tăng của bản tổng hợp tháng.
    id = models.BigAutoField(primary_key=True, db_column='Ma_tong_hop')

    # Tháng/năm lấy trực tiếp từ dữ liệu tổng hợp và lịch chấm công.
    # Nhân viên được tổng hợp; nhân viên.attendance_summaries.all() lấy lịch sử tổng hợp.
    nhan_vien = models.ForeignKey(
        'employees.NhanVien', on_delete=models.CASCADE,
        related_name='attendance_summaries',
        db_column='Ma_nhan_vien',
    )
    # Tháng/năm của kết quả tổng hợp, phải khớp kỳ liên kết.
    thang = models.PositiveSmallIntegerField(db_column='Thang')
    nam = models.PositiveSmallIntegerField(db_column='Nam')
    # Tổng công chuẩn của lịch tháng, dùng làm căn cứ tính lương theo công.
    cong_chuan = models.DecimalField(max_digits=14, decimal_places=4, default=0, db_column='So_cong_chuan')
    # Tổng công thực tế làm được, có thể gồm công lẻ.
    cong_thuc_te = models.DecimalField(max_digits=14, decimal_places=4, default=0, db_column='So_ngay_lam')
    # Tổng công nghỉ hưởng lương được ghi nhận.
    cong_nghi_co_luong = models.DecimalField(max_digits=14, decimal_places=4, default=0, db_column='So_ngay_nghi_co_luong')
    # Số ngày được ghi nhận nghỉ không phép.
    so_ngay_khong_phep = models.PositiveIntegerField(default=0, db_column='So_ngay_nghi_khong_phep')
    # Tổng công hưởng lương của nhân viên trong tháng.
    tong_cong = models.DecimalField(max_digits=14, decimal_places=4, default=0, db_column='Tong_cong')
    # Tổng số giờ tăng ca trong tháng.
    tong_gio_tang_ca = models.DecimalField(
        'Tổng giờ tăng ca', max_digits=14, decimal_places=4, default=0,
        db_column='Tong_gio_tang_ca',
    )
    # Số lần đi trễ và tổng số phút đi trễ của tháng.
    so_lan_tre = models.PositiveIntegerField(default=0, db_column='So_lan_di_tre')
    so_phut_tre = models.PositiveIntegerField(default=0, db_column='Tong_phut_di_tre')
    # Trạng thái tổng hợp, mặc định chờ duyệt; không phải trạng thái công ngày.
    trang_thai = models.CharField(
        max_length=12, default='pending',
        choices=[
            ('pending', 'Chờ duyệt'),
            ('approved', 'Đã duyệt'),
            ('empty', 'Chưa có dữ liệu'),
        ],
        db_column='Trang_thai',
    )
    class Meta:
        # Tên bảng tổng hợp trong database.
        db_table = 'Tong_hop_cong'
        constraints = [
            # Không tạo hai tổng hợp của cùng nhân viên trong cùng tháng/năm.
            models.UniqueConstraint(
                fields=['nhan_vien', 'nam', 'thang'],
                name='unique_employee_month_summary',
            ),
        ]
