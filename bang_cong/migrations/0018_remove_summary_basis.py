from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('attendance', '0017_erd_daily_columns')]

    operations = [
        migrations.RemoveField(model_name='tonghopcong', name='can_cu_cong'),
    ]
