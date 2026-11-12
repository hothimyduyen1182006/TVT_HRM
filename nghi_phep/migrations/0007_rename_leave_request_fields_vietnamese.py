from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('leaves', '0006_alter_leaverequest_employee_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='leaverequest',
            old_name='id',
            new_name='Ma_don',
        ),
        migrations.RenameField(
            model_name='leaverequest',
            old_name='start_date',
            new_name='Ngay_bat_dau',
        ),
        migrations.RenameField(
            model_name='leaverequest',
            old_name='end_date',
            new_name='Ngay_ket_thuc',
        ),
        migrations.RenameField(
            model_name='leaverequest',
            old_name='reason',
            new_name='Ly_do',
        ),
        migrations.RenameField(
            model_name='leaverequest',
            old_name='status',
            new_name='Trang_thai',
        ),
        migrations.RenameField(
            model_name='leaverequest',
            old_name='evidence',
            new_name='Tep_dinh_kem',
        ),
    ]
