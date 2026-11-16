from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('bonuses', '0004_tong_thuong'),
    ]

    operations = [
        migrations.RenameField('bonus', 'employee', 'nhan_vien'),
        migrations.RenameField('bonus', 'month', 'thang'),
        migrations.RenameField('bonus', 'year', 'nam'),
        migrations.RenameField('bonus', 'name', 'ten'),
        migrations.RenameField('bonus', 'bonus_type', 'loai_thuong'),
        migrations.RenameField('bonus', 'reason', 'ly_do'),
        migrations.RenameField('bonus', 'proposed_by', 'nguoi_de_xuat'),
        migrations.RenameField('bonus', 'proposed_at', 'thoi_gian_de_xuat'),
        migrations.RenameField('bonus', 'amount', 'so_tien'),
        migrations.RenameField('bonus', 'status', 'trang_thai'),
        migrations.RenameField('bonus', 'rejection_reason', 'ly_do_tu_choi'),
        migrations.RenameField('bonus', 'approved_by', 'nguoi_duyet'),
        migrations.RenameField('bonus', 'approved_at', 'thoi_gian_duyet'),
    ]
