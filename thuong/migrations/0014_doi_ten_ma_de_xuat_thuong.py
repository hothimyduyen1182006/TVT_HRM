from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('bonuses', '0013_ma_thuong_va_id_de_xuat')]

    operations = [
        migrations.RenameField(
            model_name='dexuatthuong',
            old_name='id',
            new_name='ma_de_xuat_thuong',
        ),
    ]
