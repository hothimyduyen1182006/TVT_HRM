from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def gan_ngay_nghi_vao_don(apps, schema_editor):
    NgayNghi = apps.get_model('leaves', 'NgayNghi')
    DonNghiPhep = apps.get_model('leaves', 'DonNghiPhep')
    database = schema_editor.connection.alias

    for ngay_nghi in NgayNghi.objects.using(database).all().iterator():
        don = DonNghiPhep.objects.using(database).filter(
            nhan_vien_id=ngay_nghi.nhan_vien_id,
            ngay_bat_dau__lte=ngay_nghi.ngay,
            ngay_ket_thuc__gte=ngay_nghi.ngay,
            trang_thai='da_duyet' if ngay_nghi.da_duyet else 'cho_duyet',
        ).order_by('pk').first()

        if don is None:
            don = DonNghiPhep.objects.using(database).create(
                nhan_vien_id=ngay_nghi.nhan_vien_id,
                ngay_bat_dau=ngay_nghi.ngay,
                ngay_ket_thuc=ngay_nghi.ngay,
                loai_nghi='phep_nam' if ngay_nghi.huong_luong else 'khong_luong',
                ly_do=ngay_nghi.ly_do,
                trang_thai='da_duyet' if ngay_nghi.da_duyet else 'cho_duyet',
            )

        ngay_nghi.don_nghi_phep_id = don.pk
        ngay_nghi.save(using=database, update_fields=['don_nghi_phep'])


class Migration(migrations.Migration):
    dependencies = [('leaves', '0013_vietnamese_leave_codes')]

    operations = [
        migrations.AlterModelOptions(
            name='donnghiphep',
            options={'ordering': ['-ngay_tao']},
        ),
        migrations.AlterModelOptions(
            name='ngaynghi',
            options={'ordering': ['-ngay']},
        ),
        migrations.RemoveConstraint(
            model_name='ngaynghi',
            name='unique_employee_leave_day',
        ),
        migrations.RemoveConstraint(
            model_name='ngaynghi',
            name='leave_day_full_day_only',
        ),
        migrations.AddField(
            model_name='ngaynghi',
            name='don_nghi_phep',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='cac_ngay_nghi',
                to='leaves.donnghiphep',
            ),
        ),
        migrations.RunPython(gan_ngay_nghi_vao_don, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='ngaynghi',
            name='don_nghi_phep',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='cac_ngay_nghi',
                to='leaves.donnghiphep',
            ),
        ),
        migrations.AlterField(
            model_name='donnghiphep',
            name='nguoi_duyet',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='don_nghi_phep_da_duyet',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='donnghiphep',
            name='nhan_vien',
            field=models.ForeignKey(
                db_column='Ma_nguoi_dung',
                on_delete=django.db.models.deletion.PROTECT,
                related_name='don_nghi_phep',
                to='employees.nhanvien',
            ),
        ),
        migrations.RemoveField(model_name='ngaynghi', name='da_duyet'),
        migrations.RemoveField(model_name='ngaynghi', name='nhan_vien'),
        migrations.RemoveField(model_name='ngaynghi', name='huong_luong'),
        migrations.RemoveField(model_name='ngaynghi', name='ly_do'),
        migrations.RemoveField(model_name='ngaynghi', name='so_cong'),
        migrations.RemoveField(model_name='donnghiphep', name='huong_luong'),
        migrations.AddConstraint(
            model_name='ngaynghi',
            constraint=models.UniqueConstraint(
                fields=('don_nghi_phep', 'ngay'),
                name='unique_leave_request_day',
            ),
        ),
    ]
