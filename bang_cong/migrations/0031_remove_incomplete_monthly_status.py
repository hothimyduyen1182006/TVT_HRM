from django.db import migrations


def chuyen_trang_thai_cho_chot(apps, schema_editor):
    tong_hop_cong = apps.get_model('attendance', 'TongHopCong')
    tong_hop_cong.objects.using(schema_editor.connection.alias).filter(
        trang_thai='incomplete',
    ).update(trang_thai='pending')


class Migration(migrations.Migration):
    dependencies = [
        ('attendance', '0030_attendance_closing_labels'),
    ]

    operations = [
        migrations.RunPython(chuyen_trang_thai_cho_chot, migrations.RunPython.noop),
    ]
