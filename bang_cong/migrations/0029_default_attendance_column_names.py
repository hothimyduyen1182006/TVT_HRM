from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0028_rename_chot_nguoi_duyet_column'),
    ]

    operations = [
        migrations.AlterField(
            model_name='chamcong',
            name='id',
            field=models.BigAutoField(primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name='chamcong',
            name='nhan_vien',
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                to='employees.nhanvien',
            ),
        ),
        migrations.AlterField(
            model_name='chamcong',
            name='ngay',
            field=models.DateField(verbose_name='Ngày'),
        ),
        migrations.AlterField(
            model_name='chamcong',
            name='gio_vao',
            field=models.TimeField(blank=True, null=True, verbose_name='Check-in'),
        ),
        migrations.AlterField(
            model_name='chamcong',
            name='gio_ra',
            field=models.TimeField(blank=True, null=True, verbose_name='Check-out'),
        ),
        migrations.AlterField(
            model_name='chamcong',
            name='trang_thai',
            field=models.CharField(
                choices=[
                    ('present', 'Có mặt'),
                    ('leave', 'Nghỉ phép'),
                    ('absent', 'Nghỉ không phép'),
                    ('incomplete', 'Thiếu dữ liệu'),
                ],
                max_length=15,
                verbose_name='Trạng thái',
            ),
        ),
        migrations.AlterField(
            model_name='chamcong',
            name='so_gio_lam',
            field=models.DecimalField(decimal_places=4, default=0, max_digits=8),
        ),
        migrations.AlterField(
            model_name='chamcong',
            name='so_phut_tre',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='chamcong',
            name='so_gio_tang_ca',
            field=models.DecimalField(
                decimal_places=4,
                default=0,
                max_digits=12,
                verbose_name='Giờ tăng ca',
            ),
        ),
        migrations.AlterField(
            model_name='tonghopcong',
            name='id',
            field=models.BigAutoField(primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name='tonghopcong',
            name='nhan_vien',
            field=models.ForeignKey(
                on_delete=models.CASCADE,
                to='employees.nhanvien',
            ),
        ),
        migrations.AlterField(
            model_name='tonghopcong',
            name='thang',
            field=models.PositiveSmallIntegerField(),
        ),
        migrations.AlterField(
            model_name='tonghopcong',
            name='nam',
            field=models.PositiveSmallIntegerField(),
        ),
        migrations.AlterField(
            model_name='tonghopcong',
            name='cong_chuan',
            field=models.DecimalField(decimal_places=4, default=0, max_digits=14),
        ),
        migrations.AlterField(
            model_name='tonghopcong',
            name='cong_thuc_te',
            field=models.DecimalField(decimal_places=4, default=0, max_digits=14),
        ),
        migrations.AlterField(
            model_name='tonghopcong',
            name='cong_nghi_co_luong',
            field=models.DecimalField(decimal_places=4, default=0, max_digits=14),
        ),
        migrations.AlterField(
            model_name='tonghopcong',
            name='so_ngay_khong_phep',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='tonghopcong',
            name='tong_cong',
            field=models.DecimalField(decimal_places=4, default=0, max_digits=14),
        ),
        migrations.AlterField(
            model_name='tonghopcong',
            name='tong_gio_tang_ca',
            field=models.DecimalField(
                decimal_places=4,
                default=0,
                max_digits=14,
                verbose_name='Tổng giờ tăng ca',
            ),
        ),
        migrations.AlterField(
            model_name='tonghopcong',
            name='so_lan_tre',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='tonghopcong',
            name='so_phut_tre',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='tonghopcong',
            name='trang_thai',
            field=models.CharField(
                choices=[
                    ('pending', 'Chờ duyệt'),
                    ('approved', 'Đã duyệt'),
                    ('empty', 'Chưa có dữ liệu'),
                ],
                default='pending',
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name='chotbangcong',
            name='id',
            field=models.BigAutoField(primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name='chotbangcong',
            name='tong_hop',
            field=models.OneToOneField(
                on_delete=models.PROTECT,
                to='attendance.tonghopcong',
            ),
        ),
        migrations.AlterField(
            model_name='chotbangcong',
            name='ngay_duyet',
            field=models.DateTimeField(auto_now_add=True),
        ),
    ]
