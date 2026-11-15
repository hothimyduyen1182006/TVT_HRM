from django.db import migrations


TEN_MODEL = {
    'department': 'phongban',
    'employee': 'nhanvien',
    'position': 'chucvu',
    'education': 'hocvan',
    'laborcontract': 'hopdonglaodong',
}


def cap_nhat_ten_quyen(apps, schema_editor, reverse=False):
    alias = schema_editor.connection.alias
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')

    for ten_cu, ten_moi in TEN_MODEL.items():
        nguon, dich = (ten_moi, ten_cu) if reverse else (ten_cu, ten_moi)
        content_type = ContentType.objects.using(alias).filter(
            app_label='employees', model=nguon,
        ).first()
        if not content_type:
            continue

        ContentType.objects.using(alias).filter(pk=content_type.pk).update(model=dich)
        for hanh_dong in ('add', 'change', 'delete', 'view'):
            quyen_cu = Permission.objects.using(alias).filter(
                content_type_id=content_type.pk,
                codename=f'{hanh_dong}_{nguon}',
            ).first()
            if quyen_cu:
                Permission.objects.using(alias).filter(pk=quyen_cu.pk).update(
                    codename=f'{hanh_dong}_{dich}',
                )


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0008_alter_education_options_alter_employee_options_and_more'),
        ('attendance', '0019_merge_erd_and_vietnamese_options'),
        ('payroll', '0011_retire_attendance_period'),
        ('bonuses', '0004_tong_thuong'),
        ('leaves', '0010_simplify_leave_day_units'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RenameModel(old_name='Department', new_name='PhongBan'),
        migrations.RenameModel(old_name='Employee', new_name='NhanVien'),
        migrations.RenameModel(old_name='Position', new_name='ChucVu'),
        migrations.RenameModel(old_name='Education', new_name='HocVan'),
        migrations.RenameModel(old_name='LaborContract', new_name='HopDongLaoDong'),
        migrations.RunPython(cap_nhat_ten_quyen),
    ]
