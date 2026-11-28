from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase

from bang_luong.services.can_cu_luong_service import luu_thiet_lap_luong
from bang_luong.services.tinh_luong_service import tinh_khau_tru_bao_hiem
from .forms import BieuMauThietLapLuong
from .models import ChucVu, NhanVien, PhongBan


class SalarySettingsSaveTests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_user('salary-director')
        self.actor.groups.add(Group.objects.get_or_create(name='Giám đốc')[0])
        user = get_user_model().objects.create_user('salary-employee', email='salary@example.com')
        department = PhongBan.objects.create(ma_phong_ban='SAL', ten_phong_ban='Phòng thử')
        self.position = ChucVu.objects.create(
            phong_ban=department, ten_chuc_vu='Nhân viên', he_so_luong_chuc_vu=1)
        self.employee = NhanVien.objects.create(
            nguoi_dung=user, phong_ban=department, chuc_vu=self.position,
            ma_ho_so='SAL01', ho_va_ten='Nhân viên thử', ngay_vao_lam=date(2025, 1, 1),
            luong_co_ban=10000000)
        self.payload = {
            'luong_dong_bao_hiem': '10000000',
            'ty_le_bhxh': '0.08', 'ty_le_bhyt': '0.015', 'ty_le_bhtn': '0.01',
            'can_cu_bao_hiem': 'Căn cứ kiểm thử',
            'doi_tuong_tinh_thue': 'resident_2026',
            'giam_tru_ban_than': 'True', 'can_cu_thue': 'Căn cứ kiểm thử',
            'phu_cap_an_trua': '450000', 'luong_gio_tang_ca': '56818.1818',
            'can_cu_luong_gio_tang_ca': 'Căn cứ giờ kiểm thử',
            'ma_so_bhxh': '4826001234',
        }

    def settings(self):
        form = BieuMauThietLapLuong(self.employee, data=self.payload)
        self.assertTrue(form.is_valid(), form.errors)
        return form.du_lieu_thiet_lap()

    def test_valid_settings_round_trip_and_repeated_save(self):
        settings = self.settings()
        luu_thiet_lap_luong(self.actor, self.employee, settings)
        self.employee.refresh_from_db()
        saved = self.employee.thiet_lap_luong.copy()
        self.assertNotIn('luong_dong_bao_hiem', saved)
        self.assertEqual(saved['ty_le_bao_hiem'], {'BHXH': '0.08', 'BHYT': '0.015', 'BHTN': '0.01'})
        self.assertEqual(saved['ma_so_bhxh'], '4826001234')
        self.assertNotIn('da_kiem_tra', saved)
        luu_thiet_lap_luong(self.actor, self.employee, settings)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.thiet_lap_luong, saved)

    def test_invalid_settings_do_not_overwrite_saved_values(self):
        settings = self.settings()
        luu_thiet_lap_luong(self.actor, self.employee, settings)
        self.employee.refresh_from_db()
        saved = self.employee.thiet_lap_luong.copy()
        settings['ty_le_bao_hiem']['BHXH'] = '2'
        with self.assertRaises(ValidationError):
            luu_thiet_lap_luong(self.actor, self.employee, settings)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.thiet_lap_luong, saved)

    def test_insurance_rate_is_used_as_saved(self):
        self.payload['ty_le_bhxh'] = '0.07'
        luu_thiet_lap_luong(self.actor, self.employee, self.settings())
        self.employee.refresh_from_db()
        self.employee.thiet_lap_luong['luong_dong_bao_hiem'] = '8000000'
        form = BieuMauThietLapLuong(self.employee)
        self.assertEqual(form['ty_le_bhxh'].value(), '0.07')
        self.assertEqual(form['luong_dong_bao_hiem'].value(), Decimal('4730000'))
        self.assertEqual(tinh_khau_tru_bao_hiem(self.employee), Decimal('449350'))

    def test_employee_edit_post_saves_profile_and_salary(self):
        self.client.force_login(self.actor)
        payload = {
            **self.payload, 'ho_va_ten': 'Tên đã cập nhật', 'ma_ho_so': 'SAL01',
            'ngay_sinh': '2000-03-15', 'gioi_tinh': 'Nữ', 'cccd': '048206123451',
            'so_dien_thoai': '0905123401', 'dia_chi': 'Đà Nẵng',
            'trang_thai_nv': 'Đang làm việc', 'ten_dang_nhap': 'salary-employee',
            'email': 'salary@example.com', 'trang_thai_tai_khoan': 'on',
            'phong_ban': self.employee.phong_ban_id, 'chuc_vu': self.position.pk,
            'ngay_vao_lam': '2025-01-01', 'luong_co_ban': '11000000',
        }
        response = self.client.post(f'/nhan_vien/{self.employee.pk}/edit/', payload)
        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.ho_va_ten, 'Tên đã cập nhật')
        self.assertEqual(self.employee.luong_co_ban, Decimal('11000000'))
        self.assertNotIn('luong_dong_bao_hiem', self.employee.thiet_lap_luong)
        self.assertEqual(tinh_khau_tru_bao_hiem(self.employee), Decimal('496650'))
