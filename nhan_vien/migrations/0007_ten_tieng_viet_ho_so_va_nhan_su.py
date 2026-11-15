from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('employees', '0006_rename_national_id_employee_cccd_and_more')]

    operations = [
        migrations.RemoveConstraint('department', 'one_production_overtime_department'),
        migrations.RemoveConstraint('position', 'unique_position_per_department'),
        migrations.RemoveConstraint('laborcontract', 'contract_end_on_or_after_start'),
        migrations.RenameField('department', 'code', 'ma_phong_ban'),
        migrations.RenameField('department', 'name', 'ten_phong_ban'),
        migrations.RenameField('department', 'allows_overtime', 'cho_phep_tang_ca'),
        migrations.RenameField('department', 'manager', 'truong_phong'),
        migrations.RenameField('employee', 'code', 'ma_ho_so'),
        migrations.RenameField('employee', 'user', 'nguoi_dung'),
        migrations.RenameField('employee', 'department', 'phong_ban'),
        migrations.RenameField('employee', 'position', 'chuc_vu'),
        migrations.RenameField('employee', 'base_salary', 'luong_co_ban'),
        migrations.RenameField('employee', 'payroll_settings', 'thiet_lap_luong'),
        migrations.RenameField('employee', 'is_active', 'dang_hoat_dong'),
        migrations.RenameField('position', 'department', 'phong_ban'),
        migrations.RenameField('position', 'name', 'ten_chuc_vu'),
        migrations.RenameField('position', 'salary_coefficient', 'he_so_luong_chuc_vu'),
        migrations.RenameField('education', 'employee', 'ho_so_ca_nhan'),
        migrations.RenameField('education', 'code', 'ma_hoc_van'),
        migrations.RenameField('education', 'degree', 'bang_cap'),
        migrations.RenameField('education', 'major', 'chuyen_nganh'),
        migrations.RenameField('education', 'school', 'truong_hoc'),
        migrations.RenameField('education', 'graduation_year', 'nam_tot_nghiep'),
        migrations.RenameField('education', 'certificate_file', 'tep_bang_cap'),
        migrations.RenameField('laborcontract', 'employee', 'ho_so_ca_nhan'),
        migrations.RenameField('laborcontract', 'code', 'ma_hop_dong'),
        migrations.RenameField('laborcontract', 'number', 'so_hop_dong'),
        migrations.RenameField('laborcontract', 'contract_type', 'loai_hop_dong'),
        migrations.RenameField('laborcontract', 'signed_date', 'ngay_ky'),
        migrations.RenameField('laborcontract', 'start_date', 'ngay_bat_dau'),
        migrations.RenameField('laborcontract', 'end_date', 'ngay_ket_thuc'),
        migrations.RenameField('laborcontract', 'agreed_salary', 'luong_thoa_thuan'),
        migrations.RenameField('laborcontract', 'status', 'trang_thai'),
        migrations.RenameField('laborcontract', 'contract_file', 'tep_hop_dong'),
        migrations.AlterField(
            model_name='education', name='ho_so_ca_nhan',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='hoc_van', to='employees.employee'),
        ),
        migrations.AlterField(
            model_name='laborcontract', name='ho_so_ca_nhan',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='hop_dong_lao_dong', to='employees.employee'),
        ),
        migrations.AddConstraint(
            'department', models.UniqueConstraint(condition=models.Q(cho_phep_tang_ca=True), fields=('cho_phep_tang_ca',), name='one_production_overtime_department'),
        ),
        migrations.AddConstraint(
            'position', models.UniqueConstraint(fields=('phong_ban', 'ten_chuc_vu'), name='unique_position_per_department'),
        ),
        migrations.AddConstraint(
            'laborcontract', models.CheckConstraint(
                check=models.Q(ngay_ket_thuc__isnull=True)
                | models.Q(ngay_ket_thuc__gte=models.F('ngay_bat_dau')),
                name='contract_end_on_or_after_start',
            ),
        ),
    ]
