from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0032_doi_ten_rang_buoc_tong_hop_cong'),
    ]

    operations = [
        migrations.RenameField(
            model_name='tonghopcong',
            old_name='id',
            new_name='ma_tong_hop',
        ),
        migrations.RenameField(
            model_name='chotbangcong',
            old_name='id',
            new_name='ma_chot',
        ),
    ]
