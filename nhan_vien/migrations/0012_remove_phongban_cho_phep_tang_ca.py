from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('employees', '0011_alter_nhanvien_table'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='phongban',
            name='one_production_overtime_department',
        ),
        migrations.RemoveField(
            model_name='phongban',
            name='cho_phep_tang_ca',
        ),
    ]
