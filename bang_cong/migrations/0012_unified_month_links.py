from django.db import migrations, models
import django.db.models.deletion


def noi_lai_du_lieu(apps, schema_editor):
    alias = schema_editor.connection.alias
    KyLuong = apps.get_model('payroll', 'PayrollPeriod')
    TongHop = apps.get_model('attendance', 'TongHopCong')
    Chot = apps.get_model('attendance', 'ChotBangCong')
    for ky in KyLuong.objects.using(alias).all():
        TongHop.objects.using(alias).filter(ky_cong_id=ky.attendance_period_id).update(
            thang_luong_id=ky.pk, can_cu_cong=ky.can_cu_cong,
        )
        Chot.objects.using(alias).filter(ky_cong_id=ky.attendance_period_id).update(thang_luong_id=ky.pk)


class Migration(migrations.Migration):
    dependencies = [('attendance', '0011_computed_work_calendar'), ('payroll', '0010_unified_month_data')]
    operations = [
        migrations.AddField('tonghopcong', 'can_cu_cong', models.JSONField(default=dict, blank=True, editable=False)),
        migrations.AddField('tonghopcong', 'thang_luong', models.ForeignKey('payroll.PayrollPeriod',
            null=True, on_delete=django.db.models.deletion.CASCADE, related_name='+')),
        migrations.AddField('chotbangcong', 'thang_luong', models.ForeignKey('payroll.PayrollPeriod',
            null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+')),
        migrations.RunPython(noi_lai_du_lieu, migrations.RunPython.noop),
        migrations.RemoveConstraint('tonghopcong', 'unique_employee_period_summary'),
        migrations.RemoveConstraint('chotbangcong', 'unique_employee_attendance_approval'),
        migrations.RemoveField('tonghopcong', 'ky_cong'),
        migrations.RemoveField('chotbangcong', 'ky_cong'),
        migrations.RenameField('tonghopcong', 'thang_luong', 'ky_cong'),
        migrations.RenameField('chotbangcong', 'thang_luong', 'ky_cong'),
        migrations.AlterField('tonghopcong', 'ky_cong', models.ForeignKey('payroll.PayrollPeriod',
            on_delete=django.db.models.deletion.CASCADE, related_name='summaries')),
        migrations.AlterField('chotbangcong', 'ky_cong', models.ForeignKey('payroll.PayrollPeriod',
            on_delete=django.db.models.deletion.PROTECT, related_name='employee_approvals')),
        migrations.AddConstraint('tonghopcong', models.UniqueConstraint(
            fields=['ky_cong', 'nhan_vien'], name='unique_employee_period_summary')),
        migrations.AddConstraint('chotbangcong', models.UniqueConstraint(
            fields=['ky_cong', 'nhan_vien'], name='unique_employee_attendance_approval')),
    ]
