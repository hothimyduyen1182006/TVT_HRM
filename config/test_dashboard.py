from datetime import date, time
from django.contrib.auth.models import User, Group
from django.test import TestCase
from employees.models import Department, Employee
from attendance.models import AttendancePeriod, AttendanceRecord


class DashboardTests(TestCase):
    def setUp(self):
        self.hr = User.objects.create_user('dash-hr')
        self.hr.groups.add(Group.objects.get_or_create(name='Nhân sự')[0])
        self.manager = User.objects.create_user('dash-manager')
        self.manager.groups.add(Group.objects.get_or_create(name='Trưởng phòng')[0])
        a = Department.objects.create(code='A', name='Phòng A')
        b = Department.objects.create(code='B', name='Phòng B')
        self.people = []
        for index, (department, gender) in enumerate([(a, 'Nam'), (a, 'Nữ'), (b, '')]):
            user = self.manager if index == 0 else User.objects.create_user(f'dash-person{index}')
            self.people.append(Employee.objects.create(user=user, code=f'DASH{index}', full_name=f'Người {index}',
                department=department, gender=gender, hire_date=date(2020, 1, 1), base_salary=10000000))
        a.manager = self.people[0]
        a.save()
        AttendancePeriod.objects.create(year=2026, month=1, start_time=time(8), lunch_start=time(12),
            lunch_end=time(13), end_time=time(17), standard_hours=8)
        for employee, hour in [(self.people[0], 8), (self.people[1], 9)]:
            AttendanceRecord.objects.create(employee=employee, date=date(2026, 1, 5), check_in=time(hour), status='incomplete')

    def test_statistics_use_actual_checkin_even_before_checkout(self):
        self.client.force_login(self.hr)
        response = self.client.get('/', {'date': '2026-01-05'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_employees'], 3)
        self.assertEqual(response.context['attendance_counts'], {'ontime': 1, 'late': 1, 'unchecked': 1})
        self.assertEqual([item['count'] for item in response.context['genders']], [1, 1, 1])
        self.assertEqual(AttendanceRecord.objects.count(), 2)

    def test_manager_scope_and_department_tampering(self):
        self.client.force_login(self.manager)
        response = self.client.get('/', {'date': '2026-01-05'})
        self.assertEqual(response.context['total_employees'], 2)
        self.assertNotContains(response, 'DASH2')
        response = self.client.get('/', {'date': '2026-01-05', 'department': self.people[2].department_id})
        self.assertTrue(response.context['form'].errors)
        self.assertNotContains(response, 'DASH2')

    def test_department_only_filters_list_and_bad_date_is_handled(self):
        self.client.force_login(self.hr)
        response = self.client.get('/', {'date': '2026-01-05', 'department': self.people[2].department_id})
        self.assertEqual(response.context['total_employees'], 3)
        self.assertEqual(response.context['page_obj'].paginator.count, 1)
        self.assertEqual(response.context['page_obj'][0]['employee'], self.people[2])
        response = self.client.get('/', {'date': 'bad'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)

    def test_employee_still_redirects_and_empty_scope_is_supported(self):
        self.client.force_login(self.people[1].user)
        self.assertRedirects(self.client.get('/'), '/attendance/', fetch_redirect_response=False)
        Employee.objects.update(is_active=False)
        self.client.force_login(self.hr)
        response = self.client.get('/', {'date': '2026-01-05'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_employees'], 0)

    def test_dashboard_links_and_attendance_day_filters_match_totals(self):
        self.client.force_login(self.hr)
        response = self.client.get('/', {'date': '2026-01-05'})
        self.assertContains(response, 'href="/employees/?active_as_of=2026-01-05"')
        self.assertContains(response, 'href="/departments/?date=2026-01-05"')
        expected = {'ontime': self.people[0], 'late': self.people[1], 'unchecked': self.people[2]}
        for state, employee in expected.items():
            response = self.client.get('/attendance/', {'month': 1, 'year': 2026,
                'day': '2026-01-05', 'day_state': state})
            self.assertEqual(response.status_code, 200)
            self.assertEqual([row['employee'] for row in response.context['rows']], [employee])

    def test_employee_gender_and_department_links_preserve_scope(self):
        self.client.force_login(self.hr)
        for value, expected in [('Nam', self.people[0]), ('Nữ', self.people[1]), ('unknown', self.people[2])]:
            response = self.client.get('/employees/', {'active_as_of': '2026-01-05', 'gender': value})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(list(response.context['rows']), [expected])
        self.client.force_login(self.manager)
        response = self.client.get('/departments/', {'date': '2026-01-05'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['departments']), 1)
        response = self.client.get('/employees/', {'active_as_of': '2026-01-05', 'department': self.people[2].department_id})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['rows'].exists())
        response = self.client.get('/attendance/', {'month': 1, 'year': 2026, 'day': '2026-01-05', 'day_state': 'unchecked'})
        self.assertEqual(response.context['rows'], [])
