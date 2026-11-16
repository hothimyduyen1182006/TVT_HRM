from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0021_calendar_month_without_model'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveField(
                    model_name='tonghopcong',
                    name='gio_tang_ca',
                ),
            ],
        ),
    ]
