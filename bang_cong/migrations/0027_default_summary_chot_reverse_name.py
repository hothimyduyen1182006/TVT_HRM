from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0026_default_summary_reverse_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='chotbangcong',
            name='tong_hop',
            field=models.OneToOneField(
                db_column='Ma_tong_hop',
                on_delete=models.PROTECT,
                to='attendance.tonghopcong',
            ),
        ),
    ]
