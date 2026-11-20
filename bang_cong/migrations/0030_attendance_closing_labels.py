from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0029_default_attendance_column_names'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tonghopcong',
            name='trang_thai',
            field=models.CharField(
                choices=[('pending', 'Chờ chốt'), ('approved', 'Đã chốt'), ('empty', 'Chưa có dữ liệu')],
                default='pending',
                max_length=12,
            ),
        ),
    ]
