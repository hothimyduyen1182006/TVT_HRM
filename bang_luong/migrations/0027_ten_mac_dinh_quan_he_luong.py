from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('payroll', '0026_ma_luong_tu_tang'),
    ]

    operations = [
        migrations.AlterField(
            model_name='luong',
            name='tong_hop',
            field=models.OneToOneField(
                on_delete=models.PROTECT,
                to='attendance.tonghopcong',
            ),
        ),
        migrations.AlterField(
            model_name='luong',
            name='tong_thuong',
            field=models.OneToOneField(
                on_delete=models.PROTECT,
                to='bonuses.thuong',
            ),
        ),
    ]
