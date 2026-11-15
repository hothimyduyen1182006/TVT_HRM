from decimal import Decimal

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ('leaves', '0011_update_leave_types'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='leaveday',
            name='unique_employee_leave_day',
        ),
        migrations.RemoveConstraint(
            model_name='leaveday',
            name='leave_day_full_day_only',
        ),
        migrations.RenameModel(old_name='LeaveDay', new_name='NgayNghi'),
        migrations.RenameModel(old_name='LeaveRequest', new_name='DonNghiPhep'),
        migrations.RenameField(model_name='ngaynghi', old_name='employee', new_name='nhan_vien'),
        migrations.RenameField(model_name='ngaynghi', old_name='date', new_name='ngay'),
        migrations.RenameField(model_name='ngaynghi', old_name='units', new_name='so_cong'),
        migrations.RenameField(model_name='ngaynghi', old_name='paid', new_name='huong_luong'),
        migrations.RenameField(model_name='ngaynghi', old_name='reason', new_name='ly_do'),
        migrations.RenameField(model_name='ngaynghi', old_name='approved', new_name='da_duyet'),
        migrations.RenameField(model_name='donnghiphep', old_name='Ma_don', new_name='ma_don'),
        migrations.RenameField(model_name='donnghiphep', old_name='employee', new_name='nhan_vien'),
        migrations.RenameField(model_name='donnghiphep', old_name='Ngay_bat_dau', new_name='ngay_bat_dau'),
        migrations.RenameField(model_name='donnghiphep', old_name='Ngay_ket_thuc', new_name='ngay_ket_thuc'),
        migrations.RenameField(model_name='donnghiphep', old_name='leave_type', new_name='loai_nghi'),
        migrations.RenameField(model_name='donnghiphep', old_name='paid', new_name='huong_luong'),
        migrations.RenameField(model_name='donnghiphep', old_name='Ly_do', new_name='ly_do'),
        migrations.RenameField(model_name='donnghiphep', old_name='Tep_dinh_kem', new_name='tep_dinh_kem'),
        migrations.RenameField(model_name='donnghiphep', old_name='Trang_thai', new_name='trang_thai'),
        migrations.RenameField(model_name='donnghiphep', old_name='review_note', new_name='ghi_chu_duyet'),
        migrations.RenameField(model_name='donnghiphep', old_name='created_at', new_name='ngay_tao'),
        migrations.RenameField(model_name='donnghiphep', old_name='reviewed_by', new_name='nguoi_duyet'),
        migrations.RenameField(model_name='donnghiphep', old_name='reviewed_at', new_name='ngay_duyet'),
        migrations.AddConstraint(
            model_name='ngaynghi',
            constraint=models.UniqueConstraint(
                fields=('nhan_vien', 'ngay'),
                name='unique_employee_leave_day',
            ),
        ),
        migrations.AddConstraint(
            model_name='ngaynghi',
            constraint=models.CheckConstraint(
                check=models.Q(so_cong=Decimal('1.0000')),
                name='leave_day_full_day_only',
            ),
        ),
    ]
