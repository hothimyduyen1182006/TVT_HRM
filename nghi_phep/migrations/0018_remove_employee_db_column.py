from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('leaves', '0017_set_leave_table_names'),
        ('employees', '0009_rename_models_vietnamese'),
    ]

    operations = [
        migrations.AlterField(
            model_name='donnghiphep',
            name='nhan_vien',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='don_nghi_phep',
                to='employees.nhanvien',
            ),
        ),
    ]
