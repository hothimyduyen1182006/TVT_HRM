from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0022_remove_monthly_overtime_field'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name='LichSuDieuChinhCong'),
            ],
        ),
    ]
