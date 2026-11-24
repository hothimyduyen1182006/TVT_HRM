from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('leaves', '0016_remove_unique_leave_request_day'),
    ]

    operations = [
        migrations.AlterModelTable(
            name='donnghiphep',
            table='Don_nghi_phep',
        ),
        migrations.AlterModelTable(
            name='ngaynghi',
            table='Ngay_nghi',
        ),
    ]
