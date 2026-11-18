from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0027_default_summary_chot_reverse_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='chotbangcong',
            name='nguoi_duyet',
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
