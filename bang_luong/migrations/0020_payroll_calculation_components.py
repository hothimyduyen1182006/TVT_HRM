from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('payroll', '0019_remove_luong_valid_salary_status_and_more')]

    operations = [
        migrations.AddField(
            model_name='luong', name='phu_cap',
            field=models.DecimalField(db_column='Phu_cap', decimal_places=0, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='luong', name='khau_tru_bhyt',
            field=models.DecimalField(db_column='Khau_tru_BHYT', decimal_places=0, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='luong', name='khau_tru_bhtn',
            field=models.DecimalField(db_column='Khau_tru_BHTN', decimal_places=0, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='luong', name='khau_tru_khac',
            field=models.DecimalField(db_column='Khau_tru_khac', decimal_places=0, default=0, max_digits=12),
        ),
    ]
