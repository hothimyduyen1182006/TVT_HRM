from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('payroll', '0015_normalize_salary_status_values'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='luong',
            name='valid_salary_status',
        ),
        migrations.AlterField(
            model_name='luong',
            name='trang_thai',
            field=models.CharField(
                choices=[
                    ('pending', 'Chờ HR kiểm tra'),
                    ('submitted', 'Chờ Giám đốc ký duyệt'),
                    ('approved', 'Đã duyệt'),
                    ('paid', 'Đã chi trả'),
                ],
                db_column='Trang_thai',
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name='luong',
            constraint=models.CheckConstraint(
                check=models.Q(trang_thai__in=['pending', 'submitted', 'approved', 'paid']),
                name='valid_salary_status',
            ),
        ),
    ]
