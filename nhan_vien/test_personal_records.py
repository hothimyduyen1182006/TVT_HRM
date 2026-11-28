from datetime import date, time
from decimal import Decimal
from django.contrib.auth.models import User, Group
from django.test import TestCase
from nhan_vien.models import NhanVien, PhongBan
from bang_cong.models import ChamCong, TongHopCong
from bang_luong.models import Luong
from thuong.models import Thuong
from django.utils import timezone


class ManagementPersonalRecordsTests(TestCase):
    def setUp(self):
        self.department = PhongBan.objects.create(ma_phong_ban='SELF', ten_phong_ban='Phòng bản thân')
        self.team = PhongBan.objects.create(ma_phong_ban='TEAM', ten_phong_ban='Phòng quản lý')
        self.people = []
        for index, role in enumerate(['Nhân sự', 'Giám đốc', 'Trưởng phòng', 'Nhân viên']):
            user = User.objects.create_user(f'personal{index}')
            user.groups.add(Group.objects.get_or_create(name=role)[0])
            employee = NhanVien.objects.create(nguoi_dung=user, ma_ho_so=f'SELF{index}', ho_va_ten=f'Người {index}',
                phong_ban=self.department, ngay_vao_lam=date(2020, 1, 1), luong_co_ban=10000000)
            self.people.append(employee)
        self.team.truong_phong = self.people[2]
        self.team.save()
        for employee in self.people:
            ChamCong.objects.create(nhan_vien=employee, ngay=date(2026, 1, 5),
                trang_thai='present', gio_vao=time(8), gio_ra=time(17), so_gio_lam=8)
            summary = TongHopCong.objects.create(
                nhan_vien=employee, nam=2026, thang=1, cong_chuan=1,
                cong_thuc_te=1, tong_cong=1,
            )
            bonus = Thuong.objects.create(
                nguoi_dung=employee.nguoi_dung, nam=2026, thang=1,
                trang_thai='approved', nguoi_duyet=self.people[1].nguoi_dung,
                ngay_duyet=timezone.now(),
            )
            Luong.objects.create(
                tong_hop=summary, tong_thuong=bonus, luong_co_ban=10000000,
                luong_theo_cong=10000000, luong_thuc_linh=10000000,
            )

    def test_management_roles_can_switch_to_own_records(self):
        for employee in self.people[:3]:
            with self.subTest(user=employee.nguoi_dung.username):
                self.client.force_login(employee.nguoi_dung)
                params = {'month': 1, 'year': 2026}
                for path in ['/bang_cong/', '/bang_luong/']:
                    response = self.client.get(path, params)
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, 'của tôi')
                response = self.client.get('/bang_cong/ca-nhan/', params)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['nhan_vien'], employee)
                self.assertTrue(response.context['ca_nhan'])
                self.assertFalse(response.context['can_approve'])
                self.assertFalse(response.context['can_edit'])
                self.assertEqual(response.context['tong_hop']['paid'], Decimal(1))
                response = self.client.get('/bang_luong/ca-nhan/', params)
                self.assertEqual(response.status_code, 200)
                self.assertIn(employee, [row.tong_hop.nhan_vien for row in response.context['bang_luong']])
                self.assertNotContains(response, 'data-open-dialog="pr-calculate"')

    def test_personal_attendance_ignores_other_employee_query(self):
        employee = self.people[2]
        self.client.force_login(employee.nguoi_dung)
        response = self.client.get('/bang_cong/ca-nhan/', {'thang': 1, 'nam': 2026,
            'employee': self.people[0].pk, 'department': self.team.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['nhan_vien'], employee)
        # Quyền xem bản thân không mở rộng quyền xem nhân viên phòng khác.
        self.assertEqual(self.client.get(f'/bang_cong/nhan-vien/{self.people[0].pk}/').status_code, 404)

    def test_employee_has_no_management_scope_switch(self):
        self.client.force_login(self.people[3].nguoi_dung)
        response = self.client.get('/bang_cong/ca-nhan/', {'thang': 1, 'nam': 2026})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="record-scope')

    def test_personal_attendance_filters_dates_and_displayed_status(self):
        employee = self.people[3]
        for day, minutes_late in [(date(2026, 1, 31), 10), (date(2026, 2, 2), 0), (date(2026, 2, 3), 10)]:
            ChamCong.objects.create(
                nhan_vien=employee, ngay=day, trang_thai='present',
                gio_vao=time(8, minutes_late), gio_ra=time(17), so_phut_tre=minutes_late,
            )
        self.client.force_login(employee.nguoi_dung)
        path = '/bang_cong/ca-nhan/'
        params = {'thang': 1, 'nam': 2026, 'tu_ngay': '2026-01-31', 'den_ngay': '2026-02-02'}
        response = self.client.get(path, params)
        self.assertEqual([row['ngay'] for row in response.context['cac_dong']],
                         [date(2026, 2, 2), date(2026, 1, 31)])
        response = self.client.get(path, {**params, 'trang_thai': 'late'})
        self.assertEqual([row['ngay'] for row in response.context['cac_dong']], [date(2026, 1, 31)])
        self.assertContains(response, 'value="2026-01-31"')
        self.assertContains(response, '<option value="late" selected>Đi làm trễ</option>', html=True)
        response = self.client.get(path, {**params, 'den_ngay': '2026-01-30'})
        self.assertContains(response, 'Từ ngày phải trước hoặc bằng đến ngày.')
        self.assertEqual(response.context['cac_dong'], [])

        self.client.force_login(self.people[1].nguoi_dung)
        response = self.client.get(f'/bang_cong/nhan-vien/{employee.pk}/', {**params, 'trang_thai': 'late'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="tu_ngay"')
        self.assertEqual([row['ngay'] for row in response.context['cac_dong']],
                         [date(2026, 1, 31), date(2026, 1, 5)])

    def test_employee_management_payroll_redirects_with_denied_message(self):
        employee = self.people[3]
        self.client.force_login(employee.nguoi_dung)
        response = self.client.get('/bang_luong/', {'thang': 1, 'nam': 2026,
            'employee': self.people[0].pk, 'department': self.team.pk, 'q': 'Người 0'}, follow=True)
        self.assertEqual(response.redirect_chain, [('/bang_luong/ca-nhan/', 302)])
        self.assertContains(response, 'Bạn không có quyền truy cập chức năng quản lý lương.')
        self.assertIn(employee, [row.tong_hop.nhan_vien for row in response.context['bang_luong']])
        self.assertTrue(response.context['personal'])
        self.assertNotContains(response, 'data-open-dialog="pr-calculate"')

    def test_direct_personal_payroll_does_not_show_denied_message(self):
        self.client.force_login(self.people[3].nguoi_dung)
        response = self.client.get('/bang_luong/ca-nhan/', {'thang': 1, 'nam': 2026})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Bạn không có quyền truy cập chức năng quản lý lương.')
        self.assertIn(self.people[3], [row.tong_hop.nhan_vien for row in response.context['bang_luong']])

    def test_payroll_navigation_points_to_allowed_page_for_each_role(self):
        for employee in self.people:
            with self.subTest(user=employee.nguoi_dung.username):
                self.client.force_login(employee.nguoi_dung)
                response = self.client.get('/bang_cong/ca-nhan/', {'thang': 1, 'nam': 2026})
                path = '/bang_luong/ca-nhan/' if employee == self.people[3] else '/bang_luong/'
                self.assertContains(response, f'<a href="{path}" >BẢNG LƯƠNG</a>', html=True)
                destination = self.client.get(path, {'month': 1, 'year': 2026})
                self.assertEqual(destination.status_code, 200)
                self.assertNotContains(destination, 'Bạn không có quyền truy cập chức năng quản lý lương.')

    def test_employee_redirect_without_period_and_anonymous_login_redirect(self):
        self.client.force_login(self.people[3].nguoi_dung)
        self.assertRedirects(self.client.get('/bang_luong/'), '/bang_luong/ca-nhan/', fetch_redirect_response=False)
        self.client.logout()
        self.assertRedirects(self.client.get('/bang_luong/'), '/accounts/login/?next=/bang_luong/',
                             fetch_redirect_response=False)

    def test_dashboard_is_only_available_to_management(self):
        self.client.force_login(self.people[3].nguoi_dung)
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertRedirects(self.client.get('/dashboard/'), '/bang_cong/', fetch_redirect_response=False)
        self.assertNotContains(self.client.get('/bang_cong/'), '>DASHBOARD</a>')
        for employee in self.people[:3]:
            self.client.force_login(employee.nguoi_dung)
            response = self.client.get('/')
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, '>DASHBOARD</a>')
