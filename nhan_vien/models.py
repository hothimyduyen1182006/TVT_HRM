#truy cập các cấu hình của dự án Django, cụ thể là AUTH_USER_MODEL
from django.conf import settings
#Dùng để kiểm tra phần mở rộng của tệp được tải lên. #Dùng để kiểm tra giá trị tối thiểu.
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models

# Model phòng ban; bảng thật: Phong_ban.
class PhongBan(models.Model):
    ma_phong_ban = models.CharField('Mã phòng', max_length=30, unique=True)
    ten_phong_ban = models.CharField('Tên phòng', max_length=150)
# Vì model nhân viên được khai báo sau model Phongban nên có dấu '', setnull tức khi nv là trưởng pb bị xóa thì bảng phòng ban vẫn còn, trường trưởng pb có giá trị chuyển về null
    truong_phong = models.ForeignKey('NhanVien', null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='phong_ban_duoc_quan_ly', verbose_name='Trưởng phòng') #related_name: để truy ngược từ nhân viên tìm phòng ban mà nhân viên đó được làm trưởng phòng => nhanvien.phong_ban_duoc_quan_ly.all()
    class Meta:
        db_table = 'Phong_ban'
    def __str__(self):
        return self.ten_phong_ban


class NhanVien(models.Model):
#phần tử thứ nhất là giá trị được lưu vào cơ sở dữ liệu, còn phần tử thứ hai là nhãn hiển thị cho người dùng.
    GENDER_CHOICES = [('Nam', 'Nam'), ('Nữ', 'Nữ')]
    EMPLOYMENT_STATUS_CHOICES = [
        ('Đang làm việc', 'Đang làm việc'),
        ('Tạm nghỉ', 'Tạm nghỉ'),
        ('Đã nghỉ việc', 'Đã nghỉ việc'),
    ]

    ma_ho_so = models.CharField('Mã hồ sơ', max_length=25, unique=True)
    ho_va_ten = models.CharField('Họ tên', max_length=255)
    # OneToOne: mỗi tài khoản gắn tối đa một hồ sơ; AUTH_USER_MODEL là model tài khoản Django đang dùng.
    # nhan_vien.nguoi_dung là truy xuôi; user.employee là truy ngược nhờ related_name='employee'.
    # PROTECT ngăn xóa tài khoản khi còn hồ sơ nhân viên tham chiếu đến nó.
    nguoi_dung = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                               related_name='employee', verbose_name='Tài khoản')
    phong_ban = models.ForeignKey(PhongBan, on_delete=models.PROTECT, verbose_name='Phòng ban')
    # null=True cho phép DB lưu NULL; blank=True cho phép form để trống.
    # SET_NULL: xóa chức vụ thì hồ sơ nhân viên vẫn còn, chuc_vu được đặt NULL.
    chuc_vu = models.ForeignKey('ChucVu', null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name='employees', verbose_name='Chức vụ')
    # File thật nằm dưới MEDIA_ROOT/employees/avatars/; DB chỉ lưu đường dẫn tương đối.
    # FileExtensionValidator kiểm tra đuôi file, không xác minh toàn bộ nội dung ảnh.
    hinh_anh = models.FileField('Ảnh đại diện', upload_to='employees/avatars/', blank=True,
                              validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])])
    cccd = models.CharField('CCCD', max_length=12, null=True, blank=True, unique=True)
    gioi_tinh = models.CharField('Giới tính', max_length=10, choices=GENDER_CHOICES, blank=True)
    ngay_sinh = models.DateField('Ngày sinh', null=True, blank=True)
    so_dien_thoai = models.CharField('Số điện thoại', max_length=15, null=True, blank=True, unique=True)
    dia_chi = models.CharField('Địa chỉ', max_length=255, blank=True)
    ngay_vao_lam = models.DateField('Ngày vào làm')
    # DecimalField biểu diễn số thập phân chính xác, phù hợp với tiền hơn FloatField.
    # max_digits là tổng số chữ số; decimal_places là số chữ số sau dấu thập phân.
    luong_co_ban = models.DecimalField('Lương cơ bản', max_digits=16, decimal_places=2,
                                     validators=[MinValueValidator(0)])
    # Một cột JSON chứa nhóm thiết lập lương dùng chung của nhân viên.
    # Các key bên trong (ví dụ ma_so_thue, luong_dong_bao_hiem) không phải field/cột riêng của NhanVien.
    thiet_lap_luong = models.JSONField('Thiết lập tính lương dùng chung', null=True, blank=True, default=None)
    # dang_hoat_dong phản ánh trạng thái làm việc; User.is_active là trạng thái tài khoản đăng nhập.
    dang_hoat_dong = models.BooleanField('Đang làm việc', default=True)
    trang_thai_nv = models.CharField('Trạng thái nhân viên', max_length=30,
                                         choices=EMPLOYMENT_STATUS_CHOICES,
                                         default='Đang làm việc')
    class Meta:
        ordering = ['ma_ho_so']
        db_table = 'Nhan_vien'
    def __str__(self):
        return f'{self.ma_ho_so} - {self.ho_va_ten}'


class ChucVu(models.Model):
    phong_ban = models.ForeignKey(PhongBan, on_delete=models.PROTECT, related_name='positions')
    ten_chuc_vu = models.CharField('Tên chức vụ', max_length=255)
    he_so_luong_chuc_vu = models.DecimalField('Hệ số lương chức vụ', max_digits=4,
                                             decimal_places=1, validators=[MinValueValidator(0)])
    class Meta:
        db_table = 'Chuc_vu'
        ordering = ['phong_ban__ten_phong_ban', 'ten_chuc_vu']
        # UNIQUE ghép: cùng phòng không được trùng tên chức vụ; khác phòng được trùng.
        constraints = [models.UniqueConstraint(fields=['phong_ban', 'ten_chuc_vu'], name='unique_position_per_department')]
    def __str__(self):
        return self.ten_chuc_vu


class HocVan(models.Model):
    # Một nhân viên có nhiều học vấn; nhan_vien.hoc_van.all() là truy ngược nhờ related_name.
    # CASCADE xóa bản ghi học vấn khi xóa nhân viên;
    ho_so_ca_nhan = models.ForeignKey(NhanVien, on_delete=models.CASCADE, related_name='hoc_van')
    ma_hoc_van = models.CharField('Mã học vấn', max_length=25, unique=True)
    bang_cap = models.CharField('Bằng cấp', max_length=100)
    chuyen_nganh = models.CharField('Chuyên ngành', max_length=100, blank=True)
    truong_hoc = models.CharField('Trường học', max_length=255, blank=True)
    nam_tot_nghiep = models.PositiveSmallIntegerField('Năm tốt nghiệp', null=True, blank=True)
    tep_bang_cap = models.FileField('Tệp bằng cấp', upload_to='employees/education/', blank=True,
                                        validators=[FileExtensionValidator(['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'])])
    class Meta:
        db_table = 'Hoc_van'
        # Dấu -: năm tốt nghiệp giảm dần; tiếp theo mã học vấn tăng dần.
        ordering = ['-nam_tot_nghiep', 'ma_hoc_van']
    def __str__(self):
        return f'{self.ma_hoc_van} - {self.bang_cap}'


class HopDongLaoDong(models.Model):
    STATUS_CHOICES = [('Đang hiệu lực', 'Đang hiệu lực'), ('Đã hết hiệu lực', 'Đã hết hiệu lực')]
    # ForeignKey: mỗi hợp đồng thuộc một nhân viên; một nhân viên có thể có nhiều hợp đồng.
    # nhan_vien.hop_dong_lao_dong.all() là truy ngược nhờ related_name bên dưới.
    # CASCADE xóa bản ghi hợp đồng khi xóa nhân viên
    ho_so_ca_nhan = models.ForeignKey(NhanVien, on_delete=models.CASCADE, related_name='hop_dong_lao_dong')
    ma_hop_dong = models.CharField('Mã hợp đồng', max_length=25, unique=True)
    so_hop_dong = models.CharField('Số hợp đồng', max_length=50, unique=True)
    loai_hop_dong = models.CharField('Loại hợp đồng', max_length=50)
    ngay_ky = models.DateField('Ngày ký')
    ngay_bat_dau = models.DateField('Ngày bắt đầu')
    ngay_ket_thuc = models.DateField('Ngày kết thúc', null=True, blank=True)
    luong_thoa_thuan = models.DecimalField('Lương thỏa thuận', max_digits=12, decimal_places=0,
                                        validators=[MinValueValidator(0)])
    trang_thai = models.CharField('Trạng thái', max_length=30, choices=STATUS_CHOICES, default='Đang hiệu lực')
    tep_hop_dong = models.FileField('Tệp hợp đồng', upload_to='employees/contracts/', blank=True,
                                     validators=[FileExtensionValidator(['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'])])
    class Meta:
        db_table = 'Hop_dong_lao_dong'
        # Hợp đồng bắt đầu gần đây xếp trước, rồi đến mã hợp đồng tăng dần.
        ordering = ['-ngay_bat_dau', 'ma_hop_dong']
        # CHECK thật ở database: ngày kết thúc NULL HOẶC >= ngày bắt đầu.
        # Q biểu diễn điều kiện; | là HOẶC; F tham chiếu cột ngay_bat_dau
        # của chính bản ghi; __gte là >= và __isnull kiểm tra NULL.
        constraints = [models.CheckConstraint(
            check=models.Q(ngay_ket_thuc__isnull=True) | models.Q(ngay_ket_thuc__gte=models.F('ngay_bat_dau')),
            name='contract_end_on_or_after_start',
        )]

    def __str__(self):
        return self.so_hop_dong
