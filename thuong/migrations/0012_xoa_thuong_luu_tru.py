from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('bonuses', '0011_ten_cot_khoa_ngoai')]

    operations = [
        migrations.RunSQL('DROP TABLE IF EXISTS "Thuong_luu_tru"'),
    ]
