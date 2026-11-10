from django.conf import settings
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models


class Department(models.Model):
    code = models.CharField('Mã phòng', max_length=30, unique=True)
    name = models.CharField('Tên phòng', max_length=150)
    # Retained only for historical schema compatibility; never gates automatic OT.
    allows_overtime = models.BooleanField('Phòng Sản xuất được phép OT', default=False)
    manager = models.ForeignKey('Employee', null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='managed_departments', verbose_name='Trưởng phòng')

    class Meta:
        db_table = 'Phong_ban'
        constraints = [models.UniqueConstraint(fields=['allows_overtime'], condition=models.Q(allows_overtime=True),
                                               name='one_production_overtime_department')]

    def __str__(self):
        return self.name


class Employee(models.Model):
    GENDER_CHOICES = [('Nam', 'Nam'), ('Nữ', 'Nữ')]
    EMPLOYMENT_STATUS_CHOICES = [
        ('Đang làm việc', 'Đang làm việc'),
        ('Tạm nghỉ', 'Tạm nghỉ'),
        ('Đã nghỉ việc', 'Đã nghỉ việc'),
    ]

    code = models.CharField('Mã nhân viên', max_length=25, unique=True)
    full_name = models.CharField('Họ tên', max_length=255)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                               related_name='employee', verbose_name='Tài khoản')
    department = models.ForeignKey(Department, on_delete=models.PROTECT, verbose_name='Phòng ban')
    position = models.ForeignKey('Position', null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name='employees', verbose_name='Chức vụ')
    avatar = models.FileField('Ảnh đại diện', upload_to='employees/avatars/', blank=True,
                              validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])])
    national_id = models.CharField('CCCD', max_length=12, null=True, blank=True, unique=True)
    gender = models.CharField('Giới tính', max_length=10, choices=GENDER_CHOICES, blank=True)
    date_of_birth = models.DateField('Ngày sinh', null=True, blank=True)
    phone = models.CharField('Số điện thoại', max_length=15, null=True, blank=True, unique=True)
    address = models.CharField('Địa chỉ', max_length=255, blank=True)
    hire_date = models.DateField('Ngày vào làm')
    base_salary = models.DecimalField('Lương cơ bản', max_digits=16, decimal_places=2,
                                     validators=[MinValueValidator(0)])
    is_active = models.BooleanField('Đang làm việc', default=True)
    employment_status = models.CharField('Trạng thái nhân viên', max_length=30,
                                         choices=EMPLOYMENT_STATUS_CHOICES,
                                         default='Đang làm việc')

    class Meta:
        ordering = ['code']
        db_table = 'Ho_so_ca_nhan'

    def __str__(self):
        return f'{self.code} - {self.full_name}'


class Position(models.Model):
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='positions')
    name = models.CharField('Tên chức vụ', max_length=255)
    salary_coefficient = models.DecimalField('Hệ số lương chức vụ', max_digits=4,
                                             decimal_places=1, validators=[MinValueValidator(0)])

    class Meta:
        db_table = 'Chuc_vu'
        ordering = ['department__name', 'name']
        constraints = [models.UniqueConstraint(fields=['department', 'name'], name='unique_position_per_department')]

    def __str__(self):
        return self.name


class Education(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='educations')
    code = models.CharField('Mã học vấn', max_length=25, unique=True)
    degree = models.CharField('Bằng cấp', max_length=100)
    major = models.CharField('Chuyên ngành', max_length=100, blank=True)
    school = models.CharField('Trường học', max_length=255, blank=True)
    graduation_year = models.PositiveSmallIntegerField('Năm tốt nghiệp', null=True, blank=True)
    certificate_file = models.FileField('Tệp bằng cấp', upload_to='employees/education/', blank=True,
                                        validators=[FileExtensionValidator(['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'])])

    class Meta:
        db_table = 'Hoc_van'
        ordering = ['-graduation_year', 'code']

    def __str__(self):
        return f'{self.code} - {self.degree}'


class LaborContract(models.Model):
    STATUS_CHOICES = [('Đang hiệu lực', 'Đang hiệu lực'), ('Đã hết hiệu lực', 'Đã hết hiệu lực')]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='contracts')
    code = models.CharField('Mã hợp đồng', max_length=25, unique=True)
    number = models.CharField('Số hợp đồng', max_length=50, unique=True)
    contract_type = models.CharField('Loại hợp đồng', max_length=50)
    signed_date = models.DateField('Ngày ký')
    start_date = models.DateField('Ngày bắt đầu')
    end_date = models.DateField('Ngày kết thúc', null=True, blank=True)
    agreed_salary = models.DecimalField('Lương thỏa thuận', max_digits=12, decimal_places=0,
                                        validators=[MinValueValidator(0)])
    status = models.CharField('Trạng thái', max_length=30, choices=STATUS_CHOICES, default='Đang hiệu lực')
    contract_file = models.FileField('Tệp hợp đồng', upload_to='employees/contracts/', blank=True,
                                     validators=[FileExtensionValidator(['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'])])

    class Meta:
        db_table = 'Hop_dong_lao_dong'
        ordering = ['-start_date', 'code']
        constraints = [models.CheckConstraint(
            check=models.Q(end_date__isnull=True) | models.Q(end_date__gte=models.F('start_date')),
            name='contract_end_on_or_after_start',
        )]

    def __str__(self):
        return self.number
