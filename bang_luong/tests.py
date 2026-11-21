from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.contrib.admin.models import LogEntry
from django.db import connection
from django.test import TestCase
from django.urls import reverse
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

    def tao_phieu(self, summary=None, bonus=None, status='Cho_duyet'):
        return Luong.objects.create(
            tong_hop=summary or self.summary,
            tong_thuong=bonus or self.bonus,
            luong_co_ban=8000000, luong_theo_cong=7600000,
            luong_tang_ca=0, tong_tien_thuong=0,
            khau_tru_di_tre=0, khau_tru_bhxh=0, thue_tncn=0,
            luong_thuc_linh=7600000, trang_thai=status,
        )

    def test_luong_uses_default_columns(self):
        columns = {field.column for field in Luong._meta.concrete_fields}
        self.assertEqual(columns, {
            'ma_luong', 'tong_hop_id', 'tong_thuong_id', 'luong_co_ban',
            'luong_theo_cong', 'luong_tang_ca', 'phu_cap', 'tong_tien_thuong', 'khau_tru_khac',
            'khau_tru_di_tre', 'khau_tru_bhxh', 'thue_tncn',
            'luong_thuc_linh', 'trang_thai',
        })
        self.assertEqual(Luong._meta.db_table, 'Luong')
        with connection.cursor() as cursor:
            actual_columns = connection.introspection.get_table_description(cursor, 'Luong')
        self.assertEqual({column.name for column in actual_columns}, columns)

    def test_payroll_actions_reject_post_from_wrong_role(self):
        for nguoi_dung, ten_url in (
            (self.director, 'tinh_luong'),
            (self.director, 'gui_giam_doc'),
            (self.hr, 'ky_duyet'),
        ):
            with self.subTest(ten_url=ten_url):
                self.client.force_login(nguoi_dung)
                response = self.client.post(
                    reverse(f'bang_luong:{ten_url}'), {'thang': 11, 'nam': 2026},
                )
                self.assertEqual(response.status_code, 403)

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
        response = self.client.get('/bang_luong/ca-nhan/?thang=11&nam=2026')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['bang_luong']), [own])
        self.assertEqual(self.client.get(f'/bang_luong/chi-tiet/{own.pk}/').status_code, 200)
        self.assertEqual(self.client.get(f'/bang_luong/chi-tiet/{other.pk}/').status_code, 403)

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

    def test_export_only_allows_payroll_waiting_for_director_signature(self):
        phieu = self.tao_phieu()
        self.client.force_login(self.director)
        self.assertEqual(self.client.post(f'/bang_luong/{phieu.pk}/approve/').status_code, 404)

        self.client.force_login(self.hr)
        params = {'thang': 11, 'nam': 2026}
        pending = self.client.get('/bang_luong/xuat/csv/', params)
        self.assertEqual(pending.status_code, 302)

        Luong.objects.filter(pk=phieu.pk).update(trang_thai='Cho_giam_doc_duyet')
        response = self.client.get('/bang_luong/xuat/csv/', params)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Mã nhân viên'.encode(), response.content)
        self.assertTrue(LogEntry.objects.filter(change_message__contains='csv').exists())

        Luong.objects.filter(pk=phieu.pk).update(trang_thai='Da_duyet')
        self.assertEqual(self.client.get('/bang_luong/xuat/csv/', params).status_code, 200)

    def test_auto_calculation_waits_for_documented_payroll_rules(self):
        self.client.force_login(self.hr)
        self.client.post('/bang_luong/calculate/')
        self.assertFalse(Luong.objects.exists())
    def test_calculation_uses_only_approved_bonus_total(self):
        from django.core.exceptions import ValidationError
        from bang_cong.models import ChotBangCong
        from bang_luong.services.tinh_luong_service import tinh_bang_luong
        from thuong.services.quy_trinh import duyet_bang

        ChotBangCong.objects.create(tong_hop=self.summary, nguoi_duyet=self.hr)
        self.employee.thiet_lap_luong = {
            'doi_tuong_tinh_thue': 'resident_2026',
            'luong_dong_bao_hiem': '8000000',
            'can_cu_bao_hiem': 'Thiet lap kiem thu',
            'can_cu_thue': 'Thiet lap kiem thu',
        }
        self.employee.save(update_fields=['thiet_lap_luong'])
        self.bonus.thuong_chuyen_can = 200000
        self.bonus.thuong_tham_nien = 3000000
        self.bonus.thuong_khac = 750000
        self.bonus.tong_thuong = 3950000
        for status in ['draft', 'pending', 'rejected']:
            with self.subTest(status=status):
                self.bonus.trang_thai = status
                self.bonus.ly_do_tu_choi = 'Kiem tra lai' if status == 'rejected' else ''
                self.bonus.save()
                with self.assertRaisesMessage(ValidationError, 'chưa có bảng thưởng đã duyệt'):
                    tinh_bang_luong(self.hr, 2026, 11)
                self.assertFalse(Luong.objects.exists())

        self.bonus.trang_thai = 'draft'
        self.bonus.save()
        slip = self.tao_phieu()
        Luong.objects.filter(pk=slip.pk).update(tong_tien_thuong=150000)
        self.client.force_login(self.hr)
        response = self.client.get('/bang_luong/', {'thang': 11, 'nam': 2026})
        self.assertFalse(response.context['bang_luong'].exists())

        self.bonus.trang_thai = 'pending'
        self.bonus.save()
        duyet_bang(self.bonus, self.director)
        slip.refresh_from_db()
        self.assertEqual(slip.tong_thuong_id, self.bonus.pk)
        self.assertEqual(slip.tong_tien_thuong, Decimal('150000'))

        self.assertEqual(tinh_bang_luong(self.hr, 2026, 11), 1)
        slip.refresh_from_db()
        self.assertEqual(slip.tong_tien_thuong, Decimal('3950000'))
        self.assertEqual(slip.khau_tru_bhxh, Decimal('840000'))
        self.client.force_login(self.hr)
        response = self.client.get(reverse('bang_luong:chi_tiet', args=[slip.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context['phieu'].tong_thu_nhap,
            slip.luong_theo_cong + slip.luong_tang_ca + slip.phu_cap + Decimal('3950000'),
        )
        self.assertEqual(Luong.objects.filter(tong_hop=self.summary).count(), 1)
