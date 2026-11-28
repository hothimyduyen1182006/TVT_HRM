from django.db import migrations, models


def danh_so_phieu_luong(apps, schema_editor):
    Luong = apps.get_model('payroll', 'Luong')
    phieu_luong = Luong.objects.using(schema_editor.connection.alias)
    ma_cu = list(phieu_luong.order_by('pk').values_list('pk', flat=True))

    # Chọn dãy mã số chưa trùng với bất kỳ mã cũ nào.
    cac_ma_cu = set(ma_cu)
    ma_moi = 1
    for ma in ma_cu:
        while str(ma_moi) in cac_ma_cu:
            ma_moi += 1
        phieu_luong.filter(pk=ma).update(ma_luong=str(ma_moi))
        ma_moi += 1


class Migration(migrations.Migration):
    dependencies = [
        ('payroll', '0025_default_payroll_column_names'),
    ]

    operations = [
        migrations.RunPython(danh_so_phieu_luong),
        migrations.AlterField(
            model_name='luong',
            name='ma_luong',
            field=models.BigAutoField(primary_key=True, serialize=False),
        ),
    ]
