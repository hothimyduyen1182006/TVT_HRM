from datetime import date, time
from decimal import Decimal
from django.contrib.auth.models import User, Group
from django.test import TestCase
from employees.models import Employee, Department
from attendance.models import AttendancePeriod, AttendanceRecord, WorkCalendarDay
from payroll.models import PayrollPeriod, PayrollRecord


class ManagementPersonalRecordsTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(code='SELF', name='Phòng bản thân')
        self.team = Department.objects.create(code='TEAM', name='Phòng quản lý')
        self.people = []
        for index, role in enumerate(['Nhân sự', 'Giám đốc', 'Trưởng phòng', 'Nhân viên']):
            user = User.objects.create_user(f'personal{index}')
            user.groups.add(Group.objects.get_or_create(name=role)[0])
            employee = Employee.objects.create(user=user, code=f'SELF{index}', full_name=f'Người {index}',
                department=self.department, hire_date=date(2020, 1, 1), base_salary=10000000)
            self.people.append(employee)
        self.team.manager = self.people[2]
        self.team.save()
        self.period = AttendancePeriod.objects.create(year=2026, month=1, start_time=time(8),
            lunch_start=time(12), lunch_end=time(13), end_time=time(17), standard_hours=8)
        WorkCalendarDay.objects.create(date=date(2026, 1, 5), kind='work', expected_units=1)
        payroll = PayrollPeriod.objects.create(attendance_period=self.period)
        for employee in self.people:
            AttendanceRecord.objects.create(employee=employee, date=date(2026, 1, 5),
                status='present', check_in=time(8), check_out=time(17), paid_units=1, actual_units=1, work_hours=8)
            values = dict(employee=employee, period=payroll, employee_code=employee.code,
                employee_name=employee.full_name, department_id_snapshot=self.department.pk,
                department_name=self.department.name, base_salary=10000000, standard_units=1,
                paid_units=1, leave_units=0, late_minutes=0, ot_hours=0, attendance_pay=10000000,
                ot_pay=0, bonus_pay=0, allowance=0, insurance=0, tax=0, deductions=0,
                net_pay=10000000, breakdown={})
            PayrollRecord.objects.create(**values)

    def test_management_roles_can_switch_to_own_records(self):
        for employee in self.people[:3]:
            with self.subTest(user=employee.user.username):
                self.client.force_login(employee.user)
                params = {'month': 1, 'year': 2026}
                for path in ['/attendance/', '/payroll/']:
                    response = self.client.get(path, params)
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, 'của tôi')
                response = self.client.get('/attendance/personal/', params)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['employee'], employee)
                self.assertTrue(response.context['personal'])
                self.assertFalse(response.context['can_approve'])
                self.assertFalse(response.context['can_edit'])
                self.assertEqual(response.context['summary']['paid'], Decimal(1))
                self.assertEqual(self.client.get(f'/attendance/employee/{employee.pk}/history/', params).status_code, 200)
                response = self.client.get('/payroll/personal/', params)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['row'].employee, employee)
                self.assertNotContains(response, 'data-open-dialog="pr-calculate"')

    def test_personal_attendance_ignores_other_employee_query(self):
        employee = self.people[2]
        self.client.force_login(employee.user)
        response = self.client.get('/attendance/personal/', {'month': 1, 'year': 2026,
            'employee': self.people[0].pk, 'department': self.team.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['employee'], employee)
        # Quyền xem bản thân không mở rộng quyền xem nhân viên phòng khác.
        self.assertEqual(self.client.get(f'/attendance/employee/{self.people[0].pk}/').status_code, 404)

    def test_employee_has_no_management_scope_switch(self):
        self.client.force_login(self.people[3].user)
        response = self.client.get('/attendance/personal/', {'month': 1, 'year': 2026})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="record-scope')

    def test_employee_management_payroll_redirects_with_denied_message(self):
        employee = self.people[3]
        self.client.force_login(employee.user)
        response = self.client.get('/payroll/', {'month': 1, 'year': 2026,
            'employee': self.people[0].pk, 'department': self.team.pk, 'q': 'Người 0'}, follow=True)
        self.assertEqual(response.redirect_chain, [('/payroll/personal/?month=1&year=2026', 302)])
        self.assertContains(response, 'Bạn không có quyền truy cập chức năng quản lý lương.')
        self.assertEqual(response.context['row'].employee, employee)
        self.assertTrue(response.context['personal'])
        self.assertNotContains(response, 'data-open-dialog="pr-calculate"')

    def test_direct_personal_payroll_does_not_show_denied_message(self):
        self.client.force_login(self.people[3].user)
        response = self.client.get('/payroll/personal/', {'month': 1, 'year': 2026})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Bạn không có quyền truy cập chức năng quản lý lương.')
        self.assertEqual(response.context['row'].employee, self.people[3])

    def test_payroll_navigation_points_to_allowed_page_for_each_role(self):
        for employee in self.people:
            with self.subTest(user=employee.user.username):
                self.client.force_login(employee.user)
                response = self.client.get('/attendance/personal/', {'month': 1, 'year': 2026})
                path = '/payroll/personal/' if employee == self.people[3] else '/payroll/'
                self.assertContains(response, f'<a href="{path}" >BẢNG LƯƠNG</a>', html=True)
                destination = self.client.get(path, {'month': 1, 'year': 2026})
                self.assertEqual(destination.status_code, 200)
                self.assertNotContains(destination, 'Bạn không có quyền truy cập chức năng quản lý lương.')

    def test_employee_redirect_without_period_and_anonymous_login_redirect(self):
        self.client.force_login(self.people[3].user)
        self.assertRedirects(self.client.get('/payroll/'), '/payroll/personal/', fetch_redirect_response=False)
        self.client.logout()
        self.assertRedirects(self.client.get('/payroll/'), '/accounts/login/?next=/payroll/',
                             fetch_redirect_response=False)

    def test_dashboard_is_only_available_to_management(self):
        self.client.force_login(self.people[3].user)
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertRedirects(self.client.get('/dashboard/'), '/attendance/', fetch_redirect_response=False)
        self.assertNotContains(self.client.get('/attendance/'), '>DASHBOARD</a>')
        for employee in self.people[:3]:
            self.client.force_login(employee.user)
            response = self.client.get('/')
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, '>DASHBOARD</a>')
