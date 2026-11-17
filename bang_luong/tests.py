from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.contrib.admin.models import LogEntry
from django.test import TestCase
from django.utils import timezone

from bang_cong.models import TongHopCong
from bang_luong.models import Luong
from nhan_vien.access import GIAM_DOC, NHAN_SU, TRUONG_PHONG
from nhan_vien.models import NhanVien, PhongBan
from thuong.models import Thuong


class BangLuongTests(TestCase):
    def setUp(self):
        self.hr = self.tao_tai_khoan('hr', NHAN_SU)
        self.director = self.tao_tai_khoan('director', GIAM_DOC)
        self.employee_user = self.tao_tai_khoan('employee')
        self.department = PhongBan.objects.create(
            ma_phong_ban='PB1', ten_phong_ban='Phòng Một',
        )
        self.employee = self.tao_nhan_vien('NV01', self.employee_user, self.department)
        self.summary = TongHopCong.objects.create(
            nhan_vien=self.employee, thang=11, nam=2026,
            cong_chuan=20, cong_thuc_te=18, cong_nghi_co_luong=1,
            so_ngay_khong_phep=1, tong_cong=19,
            tong_gio_tang_ca=0, so_lan_tre=1, so_phut_tre=10,
            trang_thai='approved',
        )
        self.bonus = Thuong.objects.create(
            nguoi_dung=self.employee_user, thang=11, nam=2026,
            tong_thuong=0, trang_thai='approved',
            nguoi_duyet=self.director, ngay_duyet=timezone.now(),
        )

    @staticmethod
    def tao_tai_khoan(username, role=None):
        user = User.objects.create_user(username=username, password='test-pass-123')
        if role:
            user.groups.add(Group.objects.get_or_create(name=role)[0])
        return user

    @staticmethod
    def tao_nhan_vien(code, user, department):
        return NhanVien.objects.create(
            ma_ho_so=code, ho_va_ten=f'Nhân viên {code}', nguoi_dung=user,
            phong_ban=department, ngay_vao_lam=date(2020, 1, 1),
            luong_co_ban=Decimal('8000000'),
        )

    def tao_phieu(self, summary=None, bonus=None, status=Luong.CHO_DUYET):
        return Luong.objects.create(
            tong_hop=summary or self.summary,
            tong_thuong=bonus or self.bonus,
            luong_co_ban=8000000, luong_theo_cong=7600000,
            luong_tang_ca=0, tong_tien_thuong=0,
            khau_tru_di_tre=0, khau_tru_bhxh=0, thue_tncn=0,
            luong_thuc_linh=7600000, trang_thai=status,
        )

    def test_luong_uses_erd_table_and_columns(self):
        columns = {field.column for field in Luong._meta.concrete_fields}
        self.assertEqual(columns, {
            'Ma_luong', 'Ma_tong_hop', 'Ma_thuong', 'Luong_co_ban',
            'Luong_theo_cong', 'Luong_tang_ca', 'Tong_tien_thuong',
            'Khau_tru_di_tre', 'Khau_tru_BHXH', 'Thue_TNCN',
            'Luong_thuc_linh', 'Trang_thai',
        })
        self.assertEqual(Luong._meta.db_table, 'Luong')

    def test_employee_sees_only_own_personal_pay_slip(self):
        own = self.tao_phieu()
        other_user = self.tao_tai_khoan('other')
        other_employee = self.tao_nhan_vien('NV02', other_user, self.department)
        other_summary = TongHopCong.objects.create(
            nhan_vien=other_employee, thang=11, nam=2026,
            cong_chuan=20, trang_thai='approved',
        )
        other_bonus = Thuong.objects.create(
            nguoi_dung=other_user, thang=11, nam=2026, trang_thai='approved',
            nguoi_duyet=self.director, ngay_duyet=timezone.now(),
        )
        other = self.tao_phieu(other_summary, other_bonus)

        self.client.force_login(self.employee_user)
        response = self.client.get('/bang_luong/personal/?thang=11&nam=2026')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['bang_luong']), [own])
        self.assertEqual(self.client.get(f'/bang_luong/{own.pk}/').status_code, 200)
        self.assertEqual(self.client.get(f'/bang_luong/{other.pk}/').status_code, 403)

    def test_manager_filters_by_period_employee_and_status(self):
        phieu = self.tao_phieu()
        self.client.force_login(self.hr)
        response = self.client.get('/bang_luong/?month=11&year=2026&status=Cho_duyet')
        self.assertEqual(list(response.context['bang_luong']), [phieu])
        response = self.client.get('/bang_luong/?month=10&year=2026')
        self.assertFalse(response.context['bang_luong'].exists())
        response = self.client.get('/bang_luong/?month=11&year=2026&tu_khoa=no-match')
        self.assertFalse(response.context['bang_luong'].exists())

    def test_department_manager_scope_and_hr_full_scope(self):
        first = self.tao_phieu()
        other_department = PhongBan.objects.create(
            ma_phong_ban='PB2', ten_phong_ban='Phòng Hai',
        )
        second_user = self.tao_tai_khoan('second')
        second_employee = self.tao_nhan_vien('NV02', second_user, other_department)
        second_summary = TongHopCong.objects.create(
            nhan_vien=second_employee, thang=11, nam=2026,
            cong_chuan=20, trang_thai='approved',
        )
        second_bonus = Thuong.objects.create(
            nguoi_dung=second_user, thang=11, nam=2026, trang_thai='approved',
            nguoi_duyet=self.director, ngay_duyet=timezone.now(),
        )
        second = self.tao_phieu(second_summary, second_bonus)

        manager_user = self.tao_tai_khoan('manager', TRUONG_PHONG)
        manager = self.tao_nhan_vien('NV03', manager_user, self.department)
        self.department.truong_phong = manager
        self.department.save(update_fields=['truong_phong'])

        self.client.force_login(manager_user)
        response = self.client.get('/bang_luong/?thang=11&nam=2026')
        self.assertEqual(list(response.context['bang_luong']), [first])

        self.client.force_login(self.hr)
        response = self.client.get('/bang_luong/?thang=11&nam=2026')
        self.assertEqual(set(response.context['bang_luong']), {first, second})

    def test_export_is_limited_to_approved_rows_and_writes_export_log(self):
        phieu = self.tao_phieu()
        self.client.force_login(self.director)
        self.assertEqual(self.client.post(f'/bang_luong/{phieu.pk}/approve/').status_code, 404)

        self.client.force_login(self.hr)
        params = {'thang': 11, 'nam': 2026}
        pending = self.client.get('/bang_luong/export/csv/', params)
        self.assertEqual(pending.status_code, 302)

        Luong.objects.filter(pk=phieu.pk).update(trang_thai=Luong.DA_DUYET)
        response = self.client.get('/bang_luong/export/csv/', params)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Mã nhân viên'.encode(), response.content)
        self.assertTrue(LogEntry.objects.filter(change_message__contains='csv').exists())

    def test_auto_calculation_waits_for_documented_payroll_rules(self):
        self.client.force_login(self.hr)
        self.client.post('/bang_luong/calculate/')
        self.assertFalse(Luong.objects.exists())
