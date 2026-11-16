"""Dữ liệu công ngày, tổng hợp tháng và chốt công."""
# Tính số thập phân chính xác và làm tròn kết quả công.
from decimal import Decimal

from django.core.exceptions import ValidationError  # Báo dữ liệu không hợp lệ.
from django.db import models  # Các kiểu trường, quan hệ và ràng buộc database.

# Quy ước chung của các trường bên dưới:
# db_column: tên cột trong database; tên biến Python vẫn giữ nguyên.
# max_digits: tổng số chữ số; decimal_places: số chữ số sau dấu thập phân.
# default=0: giá trị ban đầu, không tự thực hiện công thức tính.
# null=True: cho phép lưu NULL; blank=True: cho phép bỏ trống trên form.
# PROTECT: chặn xóa đối tượng đang được tham chiếu.
# CASCADE: xóa kèm bản ghi liên quan, trừ khi quan hệ khác chặn việc xóa.


class ChamCong(models.Model):
    """Giờ vào/ra và kết quả tính công của một nhân viên trong một ngày."""
    # Khóa chính tự tăng, tên cột là Ma_cham_cong.
    id = models.BigAutoField(primary_key=True, db_column='Ma_cham_cong')
    # Nhân viên có bản công; employees là app label đã đăng ký.
    nhan_vien = models.ForeignKey('employees.NhanVien', on_delete=models.PROTECT, db_column='Ma_nhan_vien')
    # Ngày ghi nhận công.
    ngay = models.DateField('Ngày', db_column='Ngay_cham_cong')
    # Giờ vào/ra có thể trống khi chưa chấm công đủ.
    gio_vao = models.TimeField('Check-in', null=True, blank=True, db_column='Thoi_gian_vao')
    gio_ra = models.TimeField('Check-out', null=True, blank=True, db_column='Thoi_gian_ra')
    # choices gồm mã lưu trong database và nhãn hiển thị trên form.
    trang_thai = models.CharField(
        'Trạng thái', max_length=15,
        choices=[
            ('present', 'Có mặt'),
            ('leave', 'Nghỉ phép'),
            ('absent', 'Nghỉ không phép'),
            ('incomplete', 'Thiếu dữ liệu'),
        ],
        db_column='Trang_thai',
    )

    # Số giờ làm do service tính; lưu tối đa 8 chữ số, gồm 4 số thập phân.
    so_gio_lam = models.DecimalField(max_digits=8, decimal_places=4, default=0, db_column='So_gio_lam_viec')
    # Số phút đi trễ, là số nguyên không âm.
    so_phut_tre = models.PositiveIntegerField(default=0, db_column='Thoi_gian_di_tre')
    # Số giờ tăng ca do service tính và lưu.
    so_gio_tang_ca = models.DecimalField(
        'Giờ tăng ca', db_column='So_gio_tang_ca',
        max_digits=12, decimal_places=4, default=0,
    )


    class Meta:
        # Tên bảng thực tế và thứ tự mặc định: ngày mới trước, rồi mã nhân viên.
        db_table = 'Cham_cong'
        ordering = ['-ngay', 'nhan_vien__ma_ho_so']
        constraints = [
            # Mỗi nhân viên chỉ có một bản ghi cho một ngày.
            models.UniqueConstraint(
                fields=['nhan_vien', 'ngay'], name='unique_employee_attendance_date',
            ),
            models.CheckConstraint(
                # Q tạo điều kiện; | là HOẶC; F so sánh với cột cùng bản ghi.
                # Nếu có đủ hai giờ thì giờ ra phải sau giờ vào.
                check=(
                    models.Q(gio_ra__isnull=True)
                    | models.Q(gio_vao__isnull=True)
                    | models.Q(gio_ra__gt=models.F('gio_vao'))
                ),
                name='valid_checkout',
            ),
        ]

    def clean(self):
        # Được full_clean() hoặc ModelForm gọi; save() không tự gọi hàm này.
        # bool chuyển việc có/không có giờ thành True/False.
        co_gio_vao, co_gio_ra = bool(self.gio_vao), bool(self.gio_ra)
        # Không nhận giờ ra bằng hoặc trước giờ vào trong cùng ngày.
        if co_gio_vao and co_gio_ra and self.gio_ra <= self.gio_vao:
            raise ValidationError('Check-out phải sau check-in trong cùng ngày.')
        # Có mặt phải có đủ cả giờ vào và giờ ra.
        if self.trang_thai == 'present' and not (co_gio_vao and co_gio_ra):
            raise ValidationError('Có mặt cần đủ giờ vào và ra.')
        # Nghỉ cả ngày không được đồng thời ghi giờ làm.
        if self.trang_thai in ('leave', 'absent') and (co_gio_vao or co_gio_ra):
            raise ValidationError(
                'Có giờ làm hãy chọn Có mặt; nghỉ một phần ngày lấy từ module nghỉ phép.'
            )

    # Các @property cho phép đọc như thuộc tính, không tạo cột database.
    @property
    def cong_thuc_te(self):
        # Lấy công thực tế từ kết quả tính công ngày.
        return self._cong_ngay()['actual']

    @property
    def cong_nghi_co_luong(self):
        # Lấy công nghỉ được hưởng lương từ kết quả tính.
        return self._cong_ngay()['leave']

    def _cong_ngay(self):
        # Import tại đây để tránh vòng lặp import giữa model và service.
        from bang_cong.services.cham_cong_service import ket_qua_cong_ngay

        # Chỉ tính khi đối tượng chưa có kết quả; dùng lại trong cùng đối tượng.
        if '_ket_qua_cong' not in self.__dict__:
            self._ket_qua_cong = ket_qua_cong_ngay(self)
        return self._ket_qua_cong  # Trả kết quả đã tính hoặc được service nạp sẵn.

    @property
    def tong_cong(self):
        """Giá trị suy ra, không lưu thêm một cột trùng hai thành phần."""
        # Công thực tế + công nghỉ có lương; quantize làm tròn đến 4 số thập phân.
        return (Decimal(self.cong_thuc_te) + Decimal(self.cong_nghi_co_luong)).quantize(Decimal('0.0001'))

    @property
    def gio_tang_ca(self):
        """Tên tương thích cho giao diện/lịch sử; dùng cùng giờ OT đã lưu."""
        # Chỉ đọc giờ tăng ca đã lưu, không tính lại tăng ca ở đây.
        return Decimal(self.so_gio_tang_ca).quantize(Decimal('0.0001'))
