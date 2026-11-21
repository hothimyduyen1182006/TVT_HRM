from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('payroll', '0023_payroll_status_labels'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='luong',
            name='valid_salary_status',
        ),
    ]
