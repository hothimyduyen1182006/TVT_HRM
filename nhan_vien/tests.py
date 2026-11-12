from io import StringIO
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase
from nhan_vien.models import Employee
from bang_cong.models import ChamCong
from bang_cong.models import KyCong
from bang_luong.models import PayrollPeriod, PayrollRecord
from nghi_phep.models import LeaveRequest


class DemoDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.output = StringIO()
        call_command('seed_demo', year=2026, password='OnlyForDemoTest@2026', stdout=cls.output)

    def test_periods_sources_and_scope(self):
        self.assertEqual(Employee.objects.count(), 8)
        states = dict(PayrollPeriod.objects.values_list('attendance_period__thang', 'status'))
        self.assertEqual(states, {9: 'approved', 10: 'paid', 11: 'pending'})
        self.assertEqual(KyCong.objects.get(nam=2026, thang=11).trang_thai, 'pending')
        self.assertEqual(PayrollRecord.objects.count(), 24)
        self.assertEqual(PayrollPeriod.objects.filter(attendance_period__thang=12).count(), 0)
        for row in PayrollRecord.objects.select_related('period__attendance_period'):
            self.assertLess(row.bonus_pay, 2000000)  # Thưởng chưa duyệt không được cộng.
        manager = get_user_model().objects.get(username='demo_manager')
        self.client.force_login(manager)
        response = self.client.get('/bang_luong/?month=9&year=2026')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['rows'].count(), 2)

    def test_rerun_does_not_duplicate_or_reset_passwords(self):
        before = ChamCong.objects.count()
        user = get_user_model().objects.get(username='demo_employee')
        password_hash = user.password
        output = StringIO()
        call_command('seed_demo', year=2026, password='DifferentPassword@2026', stdout=output)
        self.assertIn('already exists', output.getvalue())
        self.assertEqual(PayrollRecord.objects.count(), 24)
        self.assertEqual(ChamCong.objects.count(), before)
        user.refresh_from_db()
        self.assertEqual(user.password, password_hash)

    def test_demo_login_and_personal_page(self):
        self.assertTrue(self.client.login(username='demo_employee', password='OnlyForDemoTest@2026'))
        response = self.client.get('/bang_luong/?month=9&year=2026', follow=True)
        self.assertContains(response, 'PHIẾU LƯƠNG CÁ NHÂN')
        self.assertContains(response, 'DEMO-NV01')
        self.assertNotContains(response, 'DEMO-NV02')
        self.assertEqual(get_user_model().objects.filter(is_superuser=True).count(), 0)

    def test_director_has_full_navigation_with_working_bonus_and_leave_pages(self):
        director = get_user_model().objects.get(username='demo_director')
        self.client.force_login(director)
        response = self.client.get('/bang_luong/?month=9&year=2026')
        for text in ['DASHBOARD', 'NHÂN VIÊN', 'BẢNG CÔNG', 'BẢNG THƯỞNG', 'BẢNG LƯƠNG', 'NGHỈ PHÉP']:
            self.assertContains(response, text)
        self.assertContains(response, 'href="/thuong/"')
        self.assertContains(response, 'href="/nghi_phep/"')
        response = self.client.get('/thuong/?month=9&year=2026')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].paginator.count, 8)
        self.assertEqual(len(response.context['rows']), 5)
        self.assertContains(response, 'aria-current="page">BẢNG THƯỞNG</a>')
        LeaveRequest.objects.create(employee=Employee.objects.get(code='DEMO-NV01'),
            Ngay_bat_dau='2026-09-10', Ngay_ket_thuc='2026-09-10', Ly_do='Test leave request')
        response = self.client.get('/nghi_phep/?month=9&year=2026')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['requests'].exists())
        self.assertContains(response, 'aria-current="page">NGHỈ PHÉP</a>')
        self.assertEqual(self.client.get('/admin/').status_code, 302)
        director.refresh_from_db()
        self.assertFalse(director.is_staff)
        self.assertFalse(director.is_superuser)

    def test_new_director_pages_do_not_expand_employee_permissions(self):
        employee = get_user_model().objects.get(username='demo_employee')
        self.client.force_login(employee)
        response = self.client.get('/')
        self.assertContains(response, 'href="/thuong/"')
        self.assertContains(response, 'href="/nghi_phep/"')
        bonuses = self.client.get('/thuong/')
        self.assertEqual(bonuses.status_code, 200)
        self.assertTrue(bonuses.context['personal'])
        self.assertTrue(all(row['employee'].user_id == employee.pk for row in bonuses.context['rows']))
        leaves = self.client.get('/nghi_phep/')
        self.assertEqual(leaves.status_code, 200)
        self.assertFalse(leaves.context['manage_view'])
        self.assertFalse(leaves.context['requests'].exclude(employee__user=employee).exists())

    def test_hr_has_full_navigation_without_director_or_admin_privileges(self):
        hr = get_user_model().objects.get(username='demo_hr')
        self.client.force_login(hr)
        response = self.client.get('/bang_cong/?month=9&year=2026')
        for text in ['DASHBOARD', 'NHÂN VIÊN', 'BẢNG CÔNG', 'BẢNG THƯỞNG', 'BẢNG LƯƠNG', 'NGHỈ PHÉP']:
            self.assertContains(response, text)
        self.assertEqual(self.client.get('/thuong/?month=9&year=2026').status_code, 200)
        self.assertEqual(self.client.get('/nghi_phep/?month=9&year=2026').status_code, 200)
        self.assertEqual(self.client.get('/admin/').status_code, 302)
        salary = PayrollRecord.objects.filter(period__attendance_period__thang=11).first()
        self.assertEqual(self.client.post(f'/bang_luong/{salary.pk}/approve/').status_code, 403)
        hr.refresh_from_db()
        self.assertFalse(hr.is_staff)
        self.assertFalse(hr.is_superuser)


class DemoCollisionTests(TestCase):
    def test_existing_username_is_not_overwritten(self):
        user = get_user_model().objects.create_user('demo_hr', password='ExistingPassword@2026')
        password_hash = user.password
        with self.assertRaises(CommandError):
            call_command('seed_demo', stdout=StringIO())
        user.refresh_from_db()
        self.assertEqual(user.password, password_hash)
        self.assertEqual(Employee.objects.count(), 0)
