from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leaves', '0009_full_day_leave_only'),
    ]

    operations = [
        migrations.AlterField(
            model_name='leaveday',
            name='units',
            field=models.DecimalField(
                decimal_places=4,
                max_digits=5,
                verbose_name='Số công nghỉ',
            ),
        ),
    ]
