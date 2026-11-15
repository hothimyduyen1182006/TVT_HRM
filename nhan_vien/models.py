from django.conf import settings
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models


class PhongBan(models.Model):
    ma_phong_ban = models.CharField('Mã phòng', max_length=30, unique=True)
    ten_phong_ban = models.CharField('Tên phòng', max_length=150)
    # Retained only for historical schema compatibility; never gates automatic OT.
    cho_phep_tang_ca = models.BooleanField('Phòng Sản xuất được phép OT', default=False)
    truong_phong = models.ForeignKey('NhanVien', null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='phong_ban_duoc_quan_ly', verbose_name='Trưởng phòng')

    class Meta:
        db_table = 'Phong_ban'
        constraints = [models.UniqueConstraint(fields=['cho_phep_tang_ca'], condition=models.Q(cho_phep_tang_ca=True),
                                               name='one_production_overtime_department')]

    def __str__(self):
        return self.ten_phong_ban


class NhanVien(models.Model):
    GENDER_CHOICES = [('Nam', 'Nam'), ('Nữ', 'Nữ')]
    EMPLOYMENT_STATUS_CHOICES = [
        ('Đang làm việc', 'Đang làm việc'),
        ('Tạm nghỉ', 'Tạm nghỉ'),
        ('Đã nghỉ việc', 'Đã nghỉ việc'),
    ]

    ma_ho_so = models.CharField('Mã hồ sơ', max_length=25, unique=True)
    ho_va_ten = models.CharField('Họ tên', max_length=255)
    nguoi_dung = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                               related_name='employee', verbose_name='Tài khoản')
    phong_ban = models.ForeignKey(PhongBan, on_delete=models.PROTECT, verbose_name='Phòng ban')
    chuc_vu = models.ForeignKey('ChucVu', null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name='employees', verbose_name='Chức vụ')
    hinh_anh = models.FileField('Ảnh đại diện', upload_to='employees/avatars/', blank=True,
                              validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])])
    cccd = models.CharField('CCCD', max_length=12, null=True, blank=True, unique=True)
    gioi_tinh = models.CharField('Giới tính', max_length=10, choices=GENDER_CHOICES, blank=True)
    ngay_sinh = models.DateField('Ngày sinh', null=True, blank=True)
    so_dien_thoai = models.CharField('Số điện thoại', max_length=15, null=True, blank=True, unique=True)
    dia_chi = models.CharField('Địa chỉ', max_length=255, blank=True)
    ngay_vao_lam = models.DateField('Ngày vào làm')
    luong_co_ban = models.DecimalField('Lương cơ bản', max_digits=16, decimal_places=2,
                                     validators=[MinValueValidator(0)])
    thiet_lap_luong = models.JSONField('Thiết lập tính lương dùng chung', null=True, blank=True, default=None)
    dang_hoat_dong = models.BooleanField('Đang làm việc', default=True)
    trang_thai_nv = models.CharField('Trạng thái nhân viên', max_length=30,
                                         choices=EMPLOYMENT_STATUS_CHOICES,
                                         default='Đang làm việc')

    class Meta:
        ordering = ['ma_ho_so']
        db_table = 'Ho_so_ca_nhan'

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
        constraints = [models.UniqueConstraint(fields=['phong_ban', 'ten_chuc_vu'], name='unique_position_per_department')]

    def __str__(self):
        return self.ten_chuc_vu


class HocVan(models.Model):
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
        ordering = ['-nam_tot_nghiep', 'ma_hoc_van']

    def __str__(self):
        return f'{self.ma_hoc_van} - {self.bang_cap}'


class HopDongLaoDong(models.Model):
    STATUS_CHOICES = [('Đang hiệu lực', 'Đang hiệu lực'), ('Đã hết hiệu lực', 'Đã hết hiệu lực')]

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
        ordering = ['-ngay_bat_dau', 'ma_hop_dong']
        constraints = [models.CheckConstraint(
            check=models.Q(ngay_ket_thuc__isnull=True) | models.Q(ngay_ket_thuc__gte=models.F('ngay_bat_dau')),
            name='contract_end_on_or_after_start',
        )]

    def __str__(self):
        return self.so_hop_dong
