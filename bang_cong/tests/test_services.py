from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bang_cong.models import ChamCong, TongHopCong
from bang_cong.services.cham_cong_service import tinh_tang_ca_tu_dong
from bang_cong.services.tong_hop_service import du_lieu_tong_hop, tong_hop_cong_thang
from bang_luong.models import Luong
from nhan_vien.access import NHAN_SU
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
        self.assertEqual(payroll.tong_hop.tong_gio_tang_ca, Decimal('7.5'))

    def test_attendance_list_filters_with_get_parameters(self):
        self.approver.groups.add(Group.objects.get_or_create(name=NHAN_SU)[0])
        self.client.force_login(self.approver)
        ChamCong.objects.create(
            nhan_vien=self.employee, ngay=date(2026, 10, 5),
            gio_vao=time(8), gio_ra=time(17), trang_thai='present',
        )
        response = self.client.get(reverse('bang_cong:danh-sach'), {
            'thang': 10, 'nam': 2026, 'phong_ban': self.employee.phong_ban_id,
            'tu_khoa': 'AT01', 'trang_thai': 'pending',
            'ngay_cham_cong': '2026-10-05', 'trang_thai_cham_cong': 'ontime',
        })

        self.assertContains(response, 'value="2026-10-05"')
        self.assertEqual([row['employee'] for row in response.context['rows']], [self.employee])

    def test_attendance_list_rejects_invalid_filter_parameters(self):
        self.approver.groups.add(Group.objects.get_or_create(name=NHAN_SU)[0])
        self.client.force_login(self.approver)
        response = self.client.get(reverse('bang_cong:danh-sach'), {
            'thang': 10, 'nam': 2026, 'phong_ban': 'khong-hop-le',
            'ngay_cham_cong': '2026-11-05',
        })

        self.assertTrue(response.context['form'].has_error('phong_ban', 'invalid_choice'))
        self.assertContains(response, 'Ngày chấm công phải thuộc tháng/năm đã chọn.')
        self.assertEqual(response.context['rows'], [])

    def test_attendance_display_and_saved_summary_use_the_same_totals(self):
        ChamCong.objects.create(
            nhan_vien=self.employee, ngay=date(2026, 10, 5),
            gio_vao=time(8, 15), gio_ra=time(18), trang_thai='present',
            so_phut_tre=15, so_gio_tang_ca=Decimal('1'),
        )
        empty_employee = NhanVien.objects.create(
            nguoi_dung=self.approver, ma_ho_so='AT02', ho_va_ten='Nhân viên mới',
            phong_ban=self.employee.phong_ban, ngay_vao_lam=date(2020, 1, 1),
            luong_co_ban=10000000,
        )

        with self.assertNumQueries(3):
            row, empty_row = tong_hop_cong_thang([self.employee, empty_employee], 2026, 10)
        data = du_lieu_tong_hop(self.employee, 2026, 10)
        self.assertEqual(row['paid'], data['tong_cong'])
        self.assertEqual(row['overtime'], data['tong_gio_tang_ca'])
        self.assertEqual(row['late'], data['so_phut_tre'])
        self.assertEqual(row['state'], data['trang_thai'])
        self.assertEqual(empty_row['state'], 'empty')

    def test_attendance_list_shows_all_matching_employees_without_pagination(self):
        self.approver.groups.add(Group.objects.get_or_create(name=NHAN_SU)[0])
        self.client.force_login(self.approver)
        for number in range(2, 17):
            nhan_vien = NhanVien.objects.create(
                nguoi_dung=get_user_model().objects.create_user(f'attendance-{number}'),
                ma_ho_so=f'AT{number:02}', ho_va_ten='Nhân viên kiểm thử',
                phong_ban_id=self.employee.phong_ban_id, ngay_vao_lam=date(2020, 1, 1),
                luong_co_ban=10000000,
            )
        ChamCong.objects.create(
            nhan_vien=nhan_vien, ngay=date(2026, 10, 5),
            gio_vao=time(8), gio_ra=time(17), trang_thai='present',
        )
        url = reverse('bang_cong:danh-sach')
        response = self.client.get(url, {'thang': 10, 'nam': 2026, 'page': 2})
        self.assertContains(response, 'AT01')
        self.assertContains(response, 'AT16')
        self.assertNotContains(response, 'aria-label="Phân trang"')
        self.assertEqual(len(response.context['rows']), 16)

        response = self.client.get(url, {'thang': 10, 'nam': 2026, 'trang_thai': 'pending'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['employee'] for row in response.context['rows']], [nhan_vien])

    def test_attendance_details_only_list_days_with_a_clock_time(self):
        ngay_vao, ngay_ra, ngay_vang = (date(2026, 10, ngay) for ngay in (5, 6, 7))
        ngay_day_du = [date(2026, 10, ngay) for ngay in range(8, 21)]
        ChamCong.objects.bulk_create([
            ChamCong(nhan_vien=self.employee, ngay=ngay_vao, gio_vao=time(8), trang_thai='incomplete'),
            ChamCong(nhan_vien=self.employee, ngay=ngay_ra, gio_ra=time(17), trang_thai='incomplete'),
            ChamCong(nhan_vien=self.employee, ngay=ngay_vang, trang_thai='absent'),
            *[
                ChamCong(nhan_vien=self.employee, ngay=ngay, gio_vao=time(8), gio_ra=time(17), trang_thai='present')
                for ngay in ngay_day_du
            ],
        ])
        self.approver.groups.add(Group.objects.get_or_create(name=NHAN_SU)[0])
        for user, url in (
            (self.user, reverse('bang_cong:ca-nhan')),
            (self.approver, reverse('bang_cong:cong-nhan-vien', args=[self.employee.pk])),
        ):
            with self.subTest(url=url):
                self.client.force_login(user)
                response = self.client.get(url, {'thang': 10, 'nam': 2026})

                self.assertContains(response, '05/10/2026')
                self.assertContains(response, '06/10/2026')
                self.assertNotContains(response, '07/10/2026')
                self.assertContains(response, '20/10/2026')
                self.assertNotContains(response, 'aria-label="Phân trang"')
                self.assertEqual(
                    [row['ngay'] for row in response.context['cac_dong']],
                    [*reversed(ngay_day_du), ngay_ra, ngay_vao],
                )
                self.assertEqual(response.context['tong_hop']['absent'], 1)
