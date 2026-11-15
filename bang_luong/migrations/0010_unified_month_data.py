from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import migrations, models
import django.db.models.deletion


def chuyen_thang(apps, schema_editor):
    KyCong = apps.get_model('attendance', 'KyCong')
    KyLuong = apps.get_model('payroll', 'PayrollPeriod')
    alias = schema_editor.connection.alias
    for ky in KyCong.objects.using(alias).all():
        thang, _ = KyLuong.objects.using(alias).get_or_create(attendance_period_id=ky.pk)
        thang.nam, thang.thang = ky.nam, ky.thang
        thang.trang_thai, thang.phien_ban = ky.trang_thai, ky.phien_ban
        thang.ds_nhan_vien = ky.ds_nhan_vien
        thang.nguoi_duyet_id, thang.ngay_duyet = ky.nguoi_duyet_id, ky.ngay_duyet
        thang.can_cu_cong = {ten: str(getattr(ky, ten)) for ten in (
            'gio_bat_dau', 'bat_dau_nghi_trua', 'ket_thuc_nghi_trua', 'gio_ket_thuc', 'gio_chuan',
        )}
        thang.can_cu_cong['lich'] = ky.lich_luu_tru
        thang.save(using=alias)


class Migration(migrations.Migration):
    dependencies = [('payroll', '0009_align_erd_columns'), ('attendance', '0011_computed_work_calendar')]
    operations = [
        migrations.AddField('payrollperiod', 'thang', models.PositiveSmallIntegerField(null=True)),
        migrations.AddField('payrollperiod', 'nam', models.PositiveSmallIntegerField(null=True)),
        migrations.AddField('payrollperiod', 'trang_thai', models.CharField(max_length=10, default='pending',
            choices=[('pending', 'Chờ duyệt'), ('approved', 'Đã duyệt')])),
        migrations.AddField('payrollperiod', 'phien_ban', models.PositiveIntegerField(default=1)),
        migrations.AddField('payrollperiod', 'ds_nhan_vien', models.JSONField(default=list, blank=True)),
        migrations.AddField('payrollperiod', 'nguoi_duyet', models.ForeignKey(settings.AUTH_USER_MODEL,
            null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name='approved_attendance_months')),
        migrations.AddField('payrollperiod', 'ngay_duyet', models.DateTimeField(null=True, blank=True)),
        migrations.AddField('payrollperiod', 'can_cu_cong', models.JSONField(default=dict, blank=True, editable=False)),
        migrations.RunPython(chuyen_thang, migrations.RunPython.noop),
        migrations.AlterField('payrollperiod', 'thang', models.PositiveSmallIntegerField(
            validators=[MinValueValidator(1), MaxValueValidator(12)])),
        migrations.AlterField('payrollperiod', 'nam', models.PositiveSmallIntegerField(
            validators=[MinValueValidator(2000), MaxValueValidator(2100)])),
        migrations.AddConstraint('payrollperiod', models.UniqueConstraint(fields=['nam', 'thang'], name='unique_salary_month')),
        migrations.AlterModelOptions('payrollperiod', {'ordering': ['-nam', '-thang']}),
    ]
