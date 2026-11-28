from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('payroll', '0027_ten_mac_dinh_quan_he_luong'),
    ]

    operations = [
        migrations.AlterField(
            model_name='luong',
            name='tong_thuong',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                to='bonuses.thuong',
            ),
        ),
    ]
