from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0025_merge_summary_and_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tonghopcong',
            name='nhan_vien',
            field=models.ForeignKey(
                db_column='Ma_nhan_vien',
                on_delete=models.CASCADE,
                to='employees.employee',
            ),
        ),
    ]
