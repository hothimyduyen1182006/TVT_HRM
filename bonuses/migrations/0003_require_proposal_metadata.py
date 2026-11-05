from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('bonuses', '0002_bonus_proposals')]

    operations = [
        migrations.AlterField(
            model_name='bonus', name='reason',
            field=models.TextField(verbose_name='Lý do'),
        ),
        migrations.AlterField(
            model_name='bonus', name='proposed_at',
            field=models.DateTimeField(blank=False, null=True),
        ),
    ]
