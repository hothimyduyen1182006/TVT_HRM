from django.db import migrations, models


def chuyen_ma_thuong(apps, schema_editor):
    Thuong = apps.get_model('bonuses', 'Thuong')
    DeXuat = apps.get_model('bonuses', 'DeXuatThuong')
    Luong = apps.get_model('payroll', 'Luong')
    LogEntry = apps.get_model('admin', 'LogEntry')
    database = schema_editor.connection.alias

    bang_thuong = Thuong.objects.using(database)
    de_xuat = DeXuat.objects.using(database)
    phieu_luong = Luong.objects.using(database)
    nhat_ky = LogEntry.objects.using(database).filter(content_type__app_label='bonuses')

    for ma_cu, nam, thang, user_id in list(
        bang_thuong.values_list('pk', 'nam', 'thang', 'nguoi_dung_id')
    ):
        ma_moi = f'MT{nam - 2000:02d}{thang:02d}-{user_id:03d}'
        if ma_cu != ma_moi:
            bang_thuong.filter(pk=ma_cu).update(ma_thuong=ma_moi)
            de_xuat.filter(bang_thuong_id=ma_cu).update(bang_thuong_id=ma_moi)
            phieu_luong.filter(tong_thuong_id=ma_cu).update(tong_thuong_id=ma_moi)
            nhat_ky.filter(content_type__model='thuong', object_id=ma_cu).update(object_id=ma_moi)

    ma_de_xuat = list(de_xuat.order_by('thoi_gian_de_xuat', 'pk').values_list('pk', flat=True))
    for id_moi, ma_cu in enumerate(ma_de_xuat, start=1):
        de_xuat.filter(pk=ma_cu).update(ma_de_xuat_thuong=str(id_moi))
        nhat_ky.filter(content_type__model='dexuatthuong', object_id=ma_cu).update(
            object_id=str(id_moi),
        )


class Migration(migrations.Migration):
    dependencies = [
        ('admin', '0003_logentry_add_action_flag_choices'),
        ('bonuses', '0012_xoa_thuong_luu_tru'),
        ('payroll', '0021_payroll_director_approval'),
    ]

    operations = [
        migrations.RunPython(chuyen_ma_thuong),
        migrations.AlterField(
            model_name='thuong',
            name='ma_thuong',
            field=models.CharField(editable=False, max_length=25, primary_key=True, serialize=False),
        ),
        migrations.RenameField(
            model_name='dexuatthuong',
            old_name='ma_de_xuat_thuong',
            new_name='id',
        ),
        migrations.AlterField(
            model_name='dexuatthuong',
            name='id',
            field=models.BigAutoField(primary_key=True, serialize=False),
        ),
    ]
