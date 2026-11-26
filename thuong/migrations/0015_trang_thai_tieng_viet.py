from django.db import migrations, models
from django.db.models import Q


TRANG_THAI = [
    ('ban_nhap', 'Bản nháp'),
    ('cho_duyet', 'Chờ duyệt'),
    ('da_duyet', 'Đã duyệt'),
    ('tu_choi', 'Từ chối'),
]
MA_CU = ['draft', 'pending', 'approved', 'rejected']
MA_MOI = [ma for ma, _ in TRANG_THAI]


def doi_ma(apps, schema_editor, cap_ma):
    bang_thuong = apps.get_model('bonuses', 'Thuong')
    ds_thuong = bang_thuong.objects.using(schema_editor.connection.alias)
    for ma_cu, ma_moi in cap_ma:
        ds_thuong.filter(trang_thai=ma_cu).update(trang_thai=ma_moi)


def chuyen_sang_tieng_viet(apps, schema_editor):
    doi_ma(apps, schema_editor, zip(MA_CU, MA_MOI))


def khoi_phuc_ma_cu(apps, schema_editor):
    doi_ma(apps, schema_editor, zip(MA_MOI, MA_CU))


class Migration(migrations.Migration):
    dependencies = [('bonuses', '0014_doi_ten_ma_de_xuat_thuong')]

    operations = [
        migrations.RemoveConstraint('thuong', 'thuong_trang_thai_hop_le'),
        migrations.RemoveConstraint('thuong', 'thuong_duyet_du_thong_tin'),
        migrations.RemoveConstraint('thuong', 'thuong_tu_choi_co_ly_do'),
        migrations.RunPython(chuyen_sang_tieng_viet, khoi_phuc_ma_cu),
        migrations.AlterField(
            model_name='thuong',
            name='trang_thai',
            field=models.CharField(max_length=30, choices=TRANG_THAI, default='ban_nhap'),
        ),
        migrations.AddConstraint(
            model_name='thuong',
            constraint=models.CheckConstraint(
                check=Q(trang_thai__in=MA_MOI), name='thuong_trang_thai_hop_le',
            ),
        ),
        migrations.AddConstraint(
            model_name='thuong',
            constraint=models.CheckConstraint(
                check=~Q(trang_thai__in=['da_duyet', 'tu_choi'])
                | Q(nguoi_duyet__isnull=False, ngay_duyet__isnull=False),
                name='thuong_duyet_du_thong_tin',
            ),
        ),
        migrations.AddConstraint(
            model_name='thuong',
            constraint=models.CheckConstraint(
                check=~Q(trang_thai='tu_choi')
                | (Q(ly_do_tu_choi__isnull=False) & ~Q(ly_do_tu_choi='')),
                name='thuong_tu_choi_co_ly_do',
            ),
        ),
    ]
