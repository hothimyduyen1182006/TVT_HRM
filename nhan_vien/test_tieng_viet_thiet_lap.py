from importlib import import_module
from types import SimpleNamespace
from datetime import time
from decimal import Decimal

from django.apps import apps
from django.db import connection

from .test_salary_settings import SalarySettingsSaveTests
from bang_luong.services.quy_trinh import can_cu_luong_nhan_vien


class ThietLapTiengVietTests(SalarySettingsSaveTests):
    def test_chuyen_du_lieu_cu_va_khoi_phuc(self):
        migration = import_module('nhan_vien.migrations.0010_tieng_viet_thiet_lap_luong')
        cu = {'insurance_base': '10000000', 'insurance_rates': {'BHXH': '0.08'},
              'verified': True, '_updated_by': self.actor.pk}
        self.employee.thiet_lap_luong = cu
        self.employee.save(update_fields=['thiet_lap_luong'])
        editor = SimpleNamespace(connection=connection)
        migration.chuyen_sang_tieng_viet(apps, editor)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.thiet_lap_luong, {
            'luong_dong_bao_hiem': '10000000', 'ty_le_bao_hiem': {'BHXH': '0.08'},
            'da_kiem_tra': True, '_updated_by': self.actor.pk})
        migration.khoi_phuc_ten_cu(apps, editor)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.thiet_lap_luong, cu)

    def test_can_cu_tinh_luong_doc_ten_moi(self):
        self.employee.thiet_lap_luong = self.settings()
        can_cu = can_cu_luong_nhan_vien(self.employee, None)
        self.assertEqual(str(can_cu.luong_dong_bao_hiem), '10000000')
        self.assertEqual(can_cu.ty_le_bao_hiem['BHXH'], '0.08')
        self.assertTrue(can_cu.da_kiem_tra)

    def test_tinh_luong_thue_bao_hiem_tang_ca_va_nguoi_phu_thuoc(self):
        from bang_cong.models import ChamCong
        from bang_cong.thang_lich import thang_lich
        from bang_cong.services.tinh_toan import lich_thang
        from bang_luong.services.tinh_toan import du_lieu_tinh_luong

        ky = thang_lich(2026, 10)
        self.employee.luong_co_ban = Decimal('30000000')
        self.employee.thiet_lap_luong = self.settings()
        self.employee.thiet_lap_luong.update(
            luong_dong_bao_hiem='30000000', luong_gio_tang_ca='100000')
        self.employee.save()
        for ngay, lich in lich_thang(2026, 10).items():
            if lich.loai_ngay == 'work':
                ChamCong.objects.create(nhan_vien=self.employee, ngay=ngay,
                                       gio_vao=time(8), gio_ra=time(17), trang_thai='present')

        for so_nguoi, thue, thuc_linh in [(0, 635000, 26665000), (1, 257500, 27042500)]:
            with self.subTest(so_nguoi=so_nguoi):
                self.employee.thiet_lap_luong['so_nguoi_phu_thuoc'] = so_nguoi
                ket_qua = du_lieu_tinh_luong(self.employee, ky, ky)
                self.assertEqual(ket_qua['thue_tncn'], Decimal(thue))
                self.assertEqual(ket_qua['luong_thuc_linh'], Decimal(thuc_linh))
                self.assertEqual(Decimal(ket_qua['chi_tiet']['insurance']['BHXH']), Decimal('2400000'))
                self.assertEqual(ket_qua['chi_tiet']['source_data']['luong_dong_bao_hiem'], '30000000')

        dong = ChamCong.objects.order_by('ngay').first()
        dong.gio_ra = time(19)
        dong.save()
        ket_qua = du_lieu_tinh_luong(self.employee, ky, ky)
        self.assertEqual(ket_qua['luong_tang_ca'], Decimal('300000'))
        self.assertEqual(ket_qua['thue_tncn'], Decimal('257500'))
        self.assertEqual(ket_qua['luong_thuc_linh'], Decimal('27342500'))

        self.employee.thiet_lap_luong['doi_tuong_tinh_thue'] = 'other'
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            du_lieu_tinh_luong(self.employee, ky, ky)

    def test_tinh_gui_duyet_va_chi_tra_voi_ten_moi(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Group
        from bang_cong.models import ChamCong, ChotBangCong
        from bang_cong.thang_lich import thang_lich
        from bang_cong.services.tinh_toan import lich_thang
        from bang_cong.services.quy_trinh import cap_nhat_tong_hop
        from bang_luong.services.tinh_toan import tinh_bang_luong
        from bang_luong.services.quy_trinh import gui_bang_luong, xu_ly_trang_thai_luong

        self.employee.thiet_lap_luong = self.settings()
        self.employee.save(update_fields=['thiet_lap_luong'])
        ky = thang_lich(2026, 10)
        for ngay, lich in lich_thang(2026, 10).items():
            if lich.loai_ngay == 'work':
                ChamCong.objects.create(nhan_vien=self.employee, ngay=ngay,
                                       gio_vao=time(8), gio_ra=time(17), trang_thai='present')
        tong_hop = cap_nhat_tong_hop(self.employee, ky)
        ChotBangCong.objects.create(tong_hop=tong_hop, nguoi_duyet=self.actor)
        tinh_bang_luong(self.actor, ky.pk, 'Kiểm tra tên thiết lập mới')
        phieu = ky.records.get()
        so_tien = phieu.luong_thuc_linh
        self.assertEqual(so_tien, Decimal('9400000'))
        nhan_su = get_user_model().objects.create_user('hr-kiem-tra-gui-luong')
        nhan_su.groups.add(Group.objects.get_or_create(name='Nhân sự')[0])
        gui_bang_luong(nhan_su, ky.pk)
        xu_ly_trang_thai_luong(self.actor, ky.pk, 'approve', 'Kiểm tra duyệt')
        xu_ly_trang_thai_luong(self.actor, ky.pk, 'paid', 'Kiểm tra chi trả', evidence='TEST')
        phieu.refresh_from_db()
        self.assertEqual(phieu.trang_thai, 'paid')
        self.assertEqual(phieu.luong_thuc_linh, so_tien)
