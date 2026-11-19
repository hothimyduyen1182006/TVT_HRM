from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from bang_cong.models import TongHopCong
from nhan_vien.access import NHAN_SU
from nhan_vien.models import NhanVien, PhongBan


class CurrentAttendanceAccessTests(TestCase):
    def setUp(self):
        self.department = PhongBan.objects.create(ma_phong_ban='AT', ten_phong_ban='Phong A')
        self.employee_user = get_user_model().objects.create_user('attendance-employee')
        self.employee = NhanVien.objects.create(
            nguoi_dung=self.employee_user, ma_ho_so='AT01', ho_va_ten='Nhan vien',
            phong_ban=self.department, ngay_vao_lam=date(2020, 1, 1), luong_co_ban=10000000,
        )
        self.hr = get_user_model().objects.create_user('attendance-hr')
        self.hr.groups.add(get_user_model().objects.get_or_create(name=NHAN_SU)[0])

    def test_employee_can_access_personal_attendance(self):
        self.client.force_login(self.employee_user)
        self.assertEqual(self.client.get('/bang_cong/ca-nhan/').status_code, 200)

    def test_hr_can_access_management_attendance(self):
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get('/bang_cong/?thang=10&nam=2026').status_code, 200)


class CurrentAttendanceSchemaTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user('schema-employee')
        department = PhongBan.objects.create(ma_phong_ban='SC', ten_phong_ban='Schema')
        self.employee = NhanVien.objects.create(
            nguoi_dung=user, ma_ho_so='SC01', ho_va_ten='Schema employee',
            phong_ban=department, ngay_vao_lam=date(2020, 1, 1), luong_co_ban=10000000,
        )

    def test_monthly_summary_uses_current_fields_and_keeps_overtime_and_late_stats(self):
        summary = TongHopCong.objects.create(
            nhan_vien=self.employee, nam=2026, thang=10,
            cong_chuan=22, cong_thuc_te=21, tong_cong=21,
            tong_gio_tang_ca='7.5', so_lan_tre=2, so_phut_tre=18,
        )

        self.assertEqual(summary.tong_gio_tang_ca, Decimal('7.5'))
        self.assertEqual(summary.so_lan_tre, 2)
        self.assertEqual(summary.so_phut_tre, 18)
