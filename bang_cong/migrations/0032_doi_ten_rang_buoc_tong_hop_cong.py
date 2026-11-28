from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0031_remove_incomplete_monthly_status'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='tonghopcong',
            name='unique_employee_month_summary',
        ),
        migrations.AddConstraint(
            model_name='tonghopcong',
            constraint=models.UniqueConstraint(
                fields=['nhan_vien', 'nam', 'thang'],
                name='tong_hop_duy_nhat_nhan_vien_thang',
            ),
        ),
    ]
