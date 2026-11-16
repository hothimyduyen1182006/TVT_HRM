from django.db import migrations, models


LOAI_NGHI_MOI = {
    'annual': 'phep_nam',
    'special_paid': 'luong_dac_biet',
    'unpaid': 'khong_luong',
}
TRANG_THAI_MOI = {
    'pending': 'cho_duyet',
    'approved': 'da_duyet',
    'rejected': 'tu_choi',
}


def doi_ma_sang_tieng_viet(apps, schema_editor):
    DonNghiPhep = apps.get_model('leaves', 'DonNghiPhep')
    database = schema_editor.connection.alias

    for ma_cu, ma_moi in LOAI_NGHI_MOI.items():
        DonNghiPhep.objects.using(database).filter(loai_nghi=ma_cu).update(loai_nghi=ma_moi)
    for ma_cu, ma_moi in TRANG_THAI_MOI.items():
        DonNghiPhep.objects.using(database).filter(trang_thai=ma_cu).update(trang_thai=ma_moi)


def doi_ma_ve_tieng_anh(apps, schema_editor):
    DonNghiPhep = apps.get_model('leaves', 'DonNghiPhep')
    database = schema_editor.connection.alias

    for ma_cu, ma_moi in LOAI_NGHI_MOI.items():
        DonNghiPhep.objects.using(database).filter(loai_nghi=ma_moi).update(loai_nghi=ma_cu)
    for ma_cu, ma_moi in TRANG_THAI_MOI.items():
        DonNghiPhep.objects.using(database).filter(trang_thai=ma_moi).update(trang_thai=ma_cu)


class Migration(migrations.Migration):
    dependencies = [('leaves', '0012_vietnamese_model_and_field_names')]

    operations = [
        migrations.RunPython(doi_ma_sang_tieng_viet, doi_ma_ve_tieng_anh),
        migrations.AlterField(
            model_name='donnghiphep',
            name='loai_nghi',
            field=models.CharField(
                choices=[
                    ('phep_nam', 'Nghỉ theo quỹ phép'),
                    ('luong_dac_biet', 'Nghỉ hưởng lương đặc biệt'),
                    ('khong_luong', 'Nghỉ không lương'),
                ],
                default='phep_nam',
                max_length=20,
                verbose_name='Loại nghỉ',
            ),
        ),
        migrations.AlterField(
            model_name='donnghiphep',
            name='trang_thai',
            field=models.CharField(
                choices=[
                    ('cho_duyet', 'Đang chờ'),
                    ('da_duyet', 'Đã duyệt'),
                    ('tu_choi', 'Từ chối'),
                    ('da_huy', 'Đã hủy'),
                ],
                default='cho_duyet',
                max_length=12,
                verbose_name='Trạng thái',
            ),
        ),
    ]
