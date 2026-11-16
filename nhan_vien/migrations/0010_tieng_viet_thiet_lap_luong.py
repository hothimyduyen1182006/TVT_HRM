from django.db import migrations


# Chỉ dùng để chuyển dữ liệu cũ; code chạy ứng dụng dùng tên tiếng Việt trực tiếp.
TEN_KHOA = {
    'insurance_number': 'ma_so_bhxh',
    'tax_code': 'ma_so_thue',
    'bank_name': 'ten_ngan_hang',
    'bank_account': 'so_tai_khoan',
    'insurance_base': 'luong_dong_bao_hiem',
    'insurance_rates': 'ty_le_bao_hiem',
    'insurance_basis': 'can_cu_bao_hiem',
    'tax_method': 'doi_tuong_tinh_thue',
    'claim_personal_deduction': 'giam_tru_ban_than',
    'tax_basis': 'can_cu_thue',
    'lunch_allowance': 'phu_cap_an_trua',
    'overtime_hourly_rate': 'luong_gio_tang_ca',
    'overtime_basis': 'can_cu_luong_gio_tang_ca',
    'verified': 'da_kiem_tra',
    'tax_dependents': 'so_nguoi_phu_thuoc',
    'tax_exempt_overtime': 'tien_tang_ca_mien_thue',
    'tax_amount': 'tien_thue',
}


def chuyen_khoa(apps, schema_editor, bang_ten):
    NhanVien = apps.get_model('employees', 'NhanVien')
    queryset = NhanVien.objects.using(schema_editor.connection.alias)
    for nhan_vien in queryset.exclude(thiet_lap_luong=None).iterator():
        du_lieu = dict(nhan_vien.thiet_lap_luong)
        for ten_cu, ten_moi in bang_ten.items():
            if ten_cu in du_lieu:
                # Nếu đã có tên mới thì giữ giá trị mới, bỏ key cũ để tránh trùng.
                du_lieu.setdefault(ten_moi, du_lieu[ten_cu])
                del du_lieu[ten_cu]
        if du_lieu != nhan_vien.thiet_lap_luong:
            queryset.filter(pk=nhan_vien.pk).update(thiet_lap_luong=du_lieu)


def chuyen_sang_tieng_viet(apps, schema_editor):
    chuyen_khoa(apps, schema_editor, TEN_KHOA)


def khoi_phuc_ten_cu(apps, schema_editor):
    chuyen_khoa(apps, schema_editor, {moi: cu for cu, moi in TEN_KHOA.items()})


class Migration(migrations.Migration):
    dependencies = [('employees', '0009_rename_models_vietnamese')]

    operations = [migrations.RunPython(chuyen_sang_tieng_viet, khoi_phuc_ten_cu)]
