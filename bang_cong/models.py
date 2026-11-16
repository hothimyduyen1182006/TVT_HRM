"""Dữ liệu công ngày, tổng hợp tháng, chốt công và lịch sử chỉnh sửa."""
# Tính số thập phân chính xác và làm tròn kết quả công.
from decimal import Decimal

from django.conf import settings  # Lấy model tài khoản qua AUTH_USER_MODEL.
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
        # Không cho ghi công trước ngày nhân viên vào làm.
        if self.nhan_vien_id and self.ngay and self.ngay < self.nhan_vien.ngay_vao_lam:
            raise ValidationError('Ngày công không được trước ngày vào làm.')
        # bool chuyển việc có/không có giờ thành True/False.
        co_gio_vao, co_gio_ra = bool(self.gio_vao), bool(self.gio_ra)
        # Cho phép ca chưa kết thúc: đã vào nhưng chưa ra, trạng thái incomplete.
        ca_dang_mo = self.trang_thai == 'incomplete' and co_gio_vao and not co_gio_ra
        # Chỉ có một giờ thì phải là ca đang mở.
        if co_gio_vao != co_gio_ra and not ca_dang_mo:
            raise ValidationError('Cần nhập đủ check-in/check-out hoặc để trống cả hai.')
        # Không nhận giờ ra bằng hoặc trước giờ vào trong cùng ngày.
        if co_gio_vao and co_gio_ra and self.gio_ra <= self.gio_vao:
            raise ValidationError('Check-out phải sau check-in trong cùng ngày.')
        # Có mặt phải có giờ; kiểm tra phía trên bảo đảm đủ cặp giờ.
        if self.trang_thai == 'present' and not co_gio_vao:
            raise ValidationError('Có mặt cần đủ giờ vào và ra.')
        # Nghỉ cả ngày không được đồng thời ghi giờ làm.
        if self.trang_thai in ('leave', 'absent') and co_gio_vao:
            raise ValidationError(
                'Có giờ làm hãy chọn Có mặt; nghỉ một phần ngày lấy từ module nghỉ phép.'
            )
        # Có đủ giờ thì phải đổi trạng thái sang Có mặt.
        if self.trang_thai == 'incomplete' and co_gio_ra:
            raise ValidationError('Có đủ giờ vào và ra hãy chọn Có mặt.')

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
        from .services.tinh_toan import ket_qua_cong_ngay

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

    @property
    def nhan_vien(self):
        # Lấy nhân viên qua tổng hợp, không lưu thêm khóa ngoại trùng.
        return self.tong_hop.nhan_vien

    @property
    def nam(self):
        return self.tong_hop.nam

    @property
    def thang(self):
        return self.tong_hop.thang


class LichSuDieuChinhCong(models.Model):
    """Một dòng cho một trường được sửa trước khi duyệt công."""
    # Khóa chính tự tăng của dòng lịch sử.
    id = models.BigAutoField(primary_key=True, db_column='Ma_dieu_chinh')
    # Bản công đã sửa; bản_công.adjustments.all() lấy các dòng lịch sử.
    cham_cong = models.ForeignKey(
        ChamCong, on_delete=models.PROTECT,
        related_name='adjustments',
        db_column='Ma_cham_cong',
    )
    # Tài khoản thực hiện chỉnh sửa công.
    nguoi_thuc_hien = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, db_column='Ma_nguoi_dieu_chinh')
    # Mã trường được sửa; mỗi trường thay đổi được ghi thành một dòng lịch sử.
    truong_dieu_chinh = models.CharField('Trường điều chỉnh', max_length=40, db_column='Truong_dieu_chinh')
    # Giá trị trước khi sửa, cho phép chuỗi rỗng.
    gia_tri_cu = models.TextField('Giá trị cũ', blank=True, db_column='Gia_tri_cu')
    # Giá trị sau khi sửa, cho phép chuỗi rỗng.
    gia_tri_moi = models.TextField('Giá trị mới', blank=True, db_column='Gia_tri_moi')
    # Lý do chỉnh sửa do người thực hiện cung cấp.
    ly_do = models.TextField('Lý do', db_column='Ly_do_dieu_chinh')
    # Service truyền thời điểm sửa vào; trường này không tự ghi thời gian.
    ngay_dieu_chinh = models.DateTimeField('Ngày điều chỉnh', db_column='Ngay_dieu_chinh')

    class Meta:
        # Tên bảng lịch sử và thứ tự mới nhất trước; cùng giờ thì mã lớn trước.
        db_table = 'Lich_su_dieu_chinh_cong'
        ordering = ['-ngay_dieu_chinh', '-pk']

    @property
    def nhan_vien(self):
        # Lấy nhân viên từ bản công liên quan, không lưu lặp trong lịch sử.
        return self.cham_cong.nhan_vien

    @property
    def ngay_cong(self):
        # Lấy ngày công từ bản công đã sửa.
        return self.cham_cong.ngay

