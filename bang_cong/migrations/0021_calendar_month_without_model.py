from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0020_merge_attendance_period_state'),
        ('payroll', '0015_normalize_salary_status_values'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RemoveConstraint(
                    model_name='tonghopcong',
                    name='unique_employee_period_summary',
                ),
                migrations.RemoveField(
                    model_name='tonghopcong',
                    name='ky_cong',
                ),
            ],
            state_operations=[
                migrations.RemoveConstraint(
                    model_name='tonghopcong',
                    name='unique_employee_period_summary',
                ),
                migrations.RemoveField(
                    model_name='tonghopcong',
                    name='ky_cong',
                ),
                migrations.DeleteModel(name='KyCong'),
            ],
        ),
    ]
