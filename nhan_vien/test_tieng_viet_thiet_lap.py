from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection

from .test_salary_settings import SalarySettingsSaveTests


class ThietLapTiengVietTests(SalarySettingsSaveTests):
    def test_chuyen_du_lieu_cu_va_khoi_phuc(self):
        migration = import_module('nhan_vien.migrations.0010_tieng_viet_thiet_lap_luong')
        cu = {
            'insurance_base': '10000000',
            'insurance_rates': {'BHXH': '0.08'},
            'verified': True,
            '_updated_by': self.actor.pk,
        }
        self.employee.thiet_lap_luong = cu
        self.employee.save(update_fields=['thiet_lap_luong'])
        editor = SimpleNamespace(connection=connection)

        migration.chuyen_sang_tieng_viet(apps, editor)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.thiet_lap_luong, {
            'luong_dong_bao_hiem': '10000000',
            'ty_le_bao_hiem': {'BHXH': '0.08'},
            'da_kiem_tra': True,
            '_updated_by': self.actor.pk,
        })

        migration.khoi_phuc_ten_cu(apps, editor)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.thiet_lap_luong, cu)
