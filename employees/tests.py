from io import StringIO
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase
from employees.models import Employee
from attendance.models import AttendanceRecord
from attendance.models import AttendancePeriod
from payroll.models import PayrollPeriod, PayrollRecord


class DemoDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.output = StringIO()
        call_command('seed_demo', year=2026, password='OnlyForDemoTest@2026', stdout=cls.output)

    def test_periods_sources_and_scope(self):
        self.assertEqual(Employee.objects.count(), 8)
        states = dict(PayrollPeriod.objects.values_list('attendance_period__month', 'status'))
        self.assertEqual(states, {9: 'approved', 10: 'paid', 11: 'pending'})
        self.assertEqual(AttendancePeriod.objects.get(year=2026, month=11).status, 'pending')
        self.assertEqual(PayrollRecord.objects.count(), 24)
        self.assertEqual(PayrollPeriod.objects.filter(attendance_period__month=12).count(), 0)
        for row in PayrollRecord.objects.select_related('period__attendance_period'):
            self.assertLess(row.bonus_pay, 2000000)  # Thưởng chưa duyệt không được cộng.
        manager = get_user_model().objects.get(username='demo_manager')
        self.client.force_login(manager)
        response = self.client.get('/payroll/?month=9&year=2026')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['rows'].count(), 2)

    def test_rerun_does_not_duplicate_or_reset_passwords(self):
        before = AttendanceRecord.objects.count()
        user = get_user_model().objects.get(username='demo_employee')
        password_hash = user.password
        output = StringIO()
        call_command('seed_demo', year=2026, password='DifferentPassword@2026', stdout=output)
        self.assertIn('already exists', output.getvalue())
        self.assertEqual(PayrollRecord.objects.count(), 24)
        self.assertEqual(AttendanceRecord.objects.count(), before)
        user.refresh_from_db()
        self.assertEqual(user.password, password_hash)

    def test_demo_login_and_personal_page(self):
        self.assertTrue(self.client.login(username='demo_employee', password='OnlyForDemoTest@2026'))
        response = self.client.get('/payroll/?month=9&year=2026')
        self.assertContains(response, 'PHIẾU LƯƠNG CÁ NHÂN')
        self.assertContains(response, 'DEMO-NV01')
        self.assertNotContains(response, 'DEMO-NV02')
        self.assertEqual(get_user_model().objects.filter(is_superuser=True).count(), 0)


class DemoCollisionTests(TestCase):
    def test_existing_username_is_not_overwritten(self):
        user = get_user_model().objects.create_user('demo_hr', password='ExistingPassword@2026')
        password_hash = user.password
        with self.assertRaises(CommandError):
            call_command('seed_demo', stdout=StringIO())
        user.refresh_from_db()
        self.assertEqual(user.password, password_hash)
        self.assertEqual(Employee.objects.count(), 0)
