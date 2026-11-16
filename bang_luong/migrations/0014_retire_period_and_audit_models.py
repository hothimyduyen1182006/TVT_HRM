from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('payroll', '0013_luong_erd_columns'),
        ('attendance', '0019_attendance_owns_period'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name='PayrollAuditLog'),
                migrations.DeleteModel(name='PayrollPeriod'),
            ],
        ),
    ]
