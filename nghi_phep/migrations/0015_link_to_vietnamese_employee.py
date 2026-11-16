from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('leaves', '0014_simplify_leave_day'),
        ('employees', '0009_rename_models_vietnamese'),
    ]

    operations = [
        migrations.AlterField(
            model_name='donnghiphep',
            name='nhan_vien',
            field=models.ForeignKey(
                db_column='Ma_nguoi_dung',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='don_nghi_phep',
                to='employees.nhanvien',
            ),
        ),
    ]
