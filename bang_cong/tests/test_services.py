from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from bang_cong.models import ChamCong, TongHopCong
from bang_cong.services.cham_cong_service import tinh_tang_ca_tu_dong
from bang_luong.models import Luong
from nhan_vien.models import NhanVien, PhongBan
from thuong.models import Thuong


class CurrentAttendancePayrollIntegrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('attendance-payroll-test')
        self.approver = get_user_model().objects.create_user('attendance-payroll-approver')
        department = PhongBan.objects.create(ma_phong_ban='AT', ten_phong_ban='Phòng A')
        self.employee = NhanVien.objects.create(
            nguoi_dung=self.user, ma_ho_so='AT01', ho_va_ten='Nhân viên',
            phong_ban=department, ngay_vao_lam=date(2020, 1, 1), luong_co_ban=10000000,
        )

    def test_overtime_calculation_uses_hours_after_five_pm(self):
        record = ChamCong.objects.create(
            nhan_vien=self.employee, ngay=date(2026, 10, 5),
            gio_vao=time(8), gio_ra=time(19), trang_thai='present',
        )
        result = tinh_tang_ca_tu_dong(record)
        self.assertEqual(result['hours'], Decimal('2.0000'))

    def test_payroll_exposes_overtime_saved_on_monthly_attendance_summary(self):
        summary = TongHopCong.objects.create(
            nhan_vien=self.employee, nam=2026, thang=10,
            cong_chuan=22, cong_thuc_te=21, tong_cong=21,
            tong_gio_tang_ca=Decimal('7.5'),
        )
        bonus = Thuong.objects.create(
            nguoi_dung=self.user, nam=2026, thang=10,
            trang_thai='approved', nguoi_duyet=self.approver,
            ngay_duyet=timezone.now(),
        )
        payroll = Luong.objects.create(
            tong_hop=summary, tong_thuong=bonus, luong_co_ban=10000000,
            luong_theo_cong=10000000, luong_thuc_linh=10000000,
        )
        self.assertEqual(payroll.so_gio_tang_ca, Decimal('7.5'))
