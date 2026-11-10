from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from employees.access import DIRECTOR, HR, MANAGER
from employees.models import Department, Employee
from .models import LeaveDay, LeaveRequest


class LeaveAccessTests(TestCase):
    """Exercise real views, templates and CSRF using Django's test database."""

    @classmethod
    def setUpTestData(cls):
        cls.department = Department.objects.create(code='LA', name='Phòng A')
        cls.other_department = Department.objects.create(code='LB', name='Phòng B')
        cls.people = {}
        for name, department, role in [
            ('employee', cls.department, 'Nhân viên'),
            ('teammate', cls.department, 'Nhân viên'),
            ('manager', cls.department, MANAGER),
            ('outsider', cls.other_department, 'Nhân viên'),
            ('hr', cls.other_department, HR),
            ('director', cls.other_department, DIRECTOR),
            ('inactive', cls.department, 'Nhân viên'),
        ]:
            user = get_user_model().objects.create_user(username=f'leave-{name}')
            user.groups.add(Group.objects.get_or_create(name=role)[0])
            cls.people[name] = Employee.objects.create(
                user=user, code=f'LEAVE-{name}', full_name=f'Nhân viên {name}',
                department=department, hire_date=date(2020, 1, 1),
                base_salary=10000000, is_active=name != 'inactive',
            )
        cls.department.manager = cls.people['manager']
        cls.department.save(update_fields=['manager'])
        cls.unlinked = get_user_model().objects.create_user(username='leave-unlinked')
        cls.unlinked.groups.add(Group.objects.get(name='Nhân viên'))
        cls.unlinked_hr = get_user_model().objects.create_user(username='leave-unlinked-hr')
        cls.unlinked_hr.groups.add(Group.objects.get(name=HR))
        cls.requests = {
            name: LeaveRequest.objects.create(
                employee=employee, start_date=date(2026, 1, 12),
                end_date=date(2026, 1, 12), reason=f'Lý do riêng của {name}',
                status='rejected' if name == 'outsider' else 'pending',
            )
            for name, employee in cls.people.items()
        }

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.url = reverse('leaves:list')

    def post(self, url, data=None, **kwargs):
        # The login page provides a real CSRF cookie even without an employee profile.
        self.client.get(reverse('login'))
        token = self.client.cookies['csrftoken'].value
        return self.client.post(url, data or {}, HTTP_X_CSRFTOKEN=token, **kwargs)

    def valid_data(self, **overrides):
        return {
            'start_date': '2026-01-20', 'end_date': '2026-01-20',
            'leave_type': 'annual', 'reason': 'Nghỉ phép theo kế hoạch', **overrides,
        }

    def assert_scope(self, response, names):
        self.assertEqual(response.status_code, 200)
        expected = {self.requests[name].pk for name in names}
        self.assertEqual(set(response.context['requests'].values_list('pk', flat=True)), expected)
        counts = response.context['counts']
        self.assertEqual(counts['total'], len(expected))
        self.assertEqual(counts['rejected'], int('outsider' in names))
        self.assertEqual(counts['pending'], len(expected) - int('outsider' in names))
        self.assertEqual(counts['approved'], 0)
        for name, item in self.requests.items():
            if name in names:
                self.assertContains(response, item.reason)
            else:
                self.assertNotContains(response, item.reason)

    def test_anonymous_get_and_post_require_login(self):
        for response in [self.client.get(self.url), self.post(self.url, self.valid_data())]:
            self.assertRedirects(response, reverse('login') + '?next=' + self.url,
                                 fetch_redirect_response=False)
        self.assertEqual(LeaveRequest.objects.count(), len(self.requests))

    def test_get_and_invalid_post_preserve_role_scopes(self):
        manager_scope = {'employee', 'teammate', 'manager', 'inactive'}
        for name, expected in [
            ('employee', {'employee'}), ('manager', manager_scope),
            ('hr', set(self.requests)), ('director', set(self.requests)),
        ]:
            with self.subTest(role=name):
                self.client.force_login(self.people[name].user)
                self.assert_scope(self.client.get(self.url), expected)
                response = self.post(self.url, {'reason': 'Thiếu ngày nghỉ'})
                self.assertTrue(response.context['form'].errors)
                self.assert_scope(response, expected)
        self.assertEqual(LeaveRequest.objects.count(), len(self.requests))

    def test_unlinked_employee_get_and_post_have_empty_scope(self):
        self.client.force_login(self.unlinked)
        self.assert_scope(self.client.get(self.url), set())
        response = self.post(self.url, self.valid_data())
        self.assert_scope(response, set())
        self.assertFalse(response.context['can_review'])
        self.assertContains(response, 'Tài khoản chưa được liên kết với hồ sơ nhân viên.')
        self.assertEqual(LeaveRequest.objects.count(), len(self.requests))

    def test_inactive_employee_get_and_post_have_empty_scope(self):
        self.client.force_login(self.people['inactive'].user)
        self.assert_scope(self.client.get(self.url), set())
        self.assert_scope(self.post(self.url, self.valid_data()), set())
        self.assertEqual(LeaveRequest.objects.count(), len(self.requests))

    def test_unlinked_hr_retains_authorized_review_scope_after_post(self):
        self.client.force_login(self.unlinked_hr)
        self.assert_scope(self.client.get(self.url), set(self.requests))
        self.assert_scope(self.post(self.url, self.valid_data()), set(self.requests))
        self.assertEqual(LeaveRequest.objects.count(), len(self.requests))

    def test_forged_and_invalid_filters_do_not_expand_scope(self):
        for user in [self.people['employee'].user, self.people['manager'].user, self.unlinked]:
            self.client.force_login(user)
            with self.subTest(user=user.username):
                url = self.url + f'?department={self.other_department.pk}'
                for response in [self.client.get(url), self.post(url, {'reason': 'Thiếu ngày'})]:
                    self.assertEqual(response.status_code, 200)
                    self.assertFalse(response.context['requests'].exists())
                    self.assertNotContains(response, self.requests['outsider'].reason)
                response = self.post(self.url + '?status=invalid', {'reason': 'Thiếu ngày'})
                self.assertTrue(response.context['filters'].errors)
                self.assertNotContains(response, self.requests['outsider'].reason)

    def test_valid_submission_uses_logged_in_employee_and_pending_status(self):
        for index, name in enumerate(['employee', 'manager', 'hr', 'director']):
            with self.subTest(role=name):
                self.client.force_login(self.people[name].user)
                response = self.post(self.url, self.valid_data(
                    start_date=f'2026-01-{20 + index}', end_date=f'2026-01-{20 + index}',
                    employee=self.people['outsider'].pk, status='approved',
                    reviewed_by=self.people['director'].user_id,
                ))
                self.assertRedirects(response, self.url)
                item = LeaveRequest.objects.get(employee=self.people[name], start_date=date(2026, 1, 20 + index))
                self.assertEqual(item.status, 'pending')
                self.assertIsNone(item.reviewed_by_id)
                self.assertTrue(item.paid)
        self.assertEqual(LeaveRequest.objects.count(), len(self.requests) + 4)
        self.assertFalse(LeaveDay.objects.exists())

    def test_model_validation_failure_preserves_own_scope(self):
        self.client.force_login(self.people['employee'].user)
        response = self.post(self.url, self.valid_data(start_date='2019-01-02', end_date='2019-01-02'))
        self.assert_scope(response, {'employee'})
        self.assertContains(response, 'Ngày nghỉ không được trước ngày vào làm.')
        self.assertEqual(LeaveRequest.objects.count(), len(self.requests))

    def test_detail_and_review_controls_follow_scope(self):
        for name in ['employee', 'manager', 'hr', 'director']:
            self.client.force_login(self.people[name].user)
            own_url = reverse('leaves:detail', args=[self.requests[name].pk])
            response = self.client.get(own_url)
            self.assertEqual(response.status_code, 200)
            review_url = reverse('leaves:review', args=[self.requests[name].pk, 'approve'])
            if name == 'employee':
                self.assertNotContains(response, f'action="{review_url}"')
            else:
                self.assertContains(response, f'action="{review_url}"')
            other_url = reverse('leaves:detail', args=[self.requests['outsider'].pk])
            self.assertEqual(self.client.get(other_url).status_code, 200 if name in ['hr', 'director'] else 404)

    def test_employee_cannot_review_even_own_request(self):
        self.client.force_login(self.people['employee'].user)
        for action in ['approve', 'reject']:
            url = reverse('leaves:review', args=[self.requests['employee'].pk, action])
            self.assertEqual(self.post(url, {'review_note': 'Đã xem xét'}).status_code, 403)
        self.requests['employee'].refresh_from_db()
        self.assertEqual(self.requests['employee'].status, 'pending')
        self.assertFalse(LeaveDay.objects.exists())

    def test_manager_cannot_review_another_department_by_direct_url(self):
        self.client.force_login(self.people['manager'].user)
        for action in ['approve', 'reject']:
            url = reverse('leaves:review', args=[self.requests['hr'].pk, action])
            self.assertEqual(self.post(url, {'review_note': 'Đã xem xét'}).status_code, 404)
        self.requests['hr'].refresh_from_db()
        self.assertEqual(self.requests['hr'].status, 'pending')
        self.assertFalse(LeaveDay.objects.exists())

    def test_authorized_roles_can_approve_and_create_leave_days(self):
        for index, name in enumerate(['manager', 'hr', 'director']):
            self.client.force_login(self.people[name].user)
            day = date(2026, 1, 21 + index)
            item = LeaveRequest.objects.create(employee=self.people['employee'],
                start_date=day, end_date=day, reason='Nghỉ phép hợp lệ', paid=True)
            url = reverse('leaves:review', args=[item.pk, 'approve'])
            self.assertRedirects(self.post(url), reverse('leaves:detail', args=[item.pk]))
            item.refresh_from_db()
            self.assertEqual(item.status, 'approved')
            self.assertEqual(item.reviewed_by_id, self.people[name].user_id)
            self.assertIsNotNone(item.reviewed_at)
            leave = LeaveDay.objects.get(employee=item.employee, date=day)
            self.assertTrue(leave.approved)
            self.assertTrue(leave.paid)

    def test_rejection_requires_reason_and_does_not_create_leave_day(self):
        self.client.force_login(self.people['manager'].user)
        item = self.requests['employee']
        url = reverse('leaves:review', args=[item.pk, 'reject'])
        self.assertRedirects(self.post(url), reverse('leaves:detail', args=[item.pk]))
        item.refresh_from_db()
        self.assertEqual(item.status, 'pending')
        self.assertRedirects(self.post(url, {'review_note': 'Cần bàn giao công việc'}),
                             reverse('leaves:detail', args=[item.pk]))
        item.refresh_from_db()
        self.assertEqual(item.status, 'rejected')
        self.assertEqual(item.review_note, 'Cần bàn giao công việc')
        self.assertFalse(LeaveDay.objects.exists())

    def test_submission_and_review_require_csrf(self):
        self.client.force_login(self.people['employee'].user)
        self.assertEqual(self.client.post(self.url, self.valid_data()).status_code, 403)
        self.assertEqual(LeaveRequest.objects.count(), len(self.requests))
        self.client.force_login(self.people['hr'].user)
        url = reverse('leaves:review', args=[self.requests['employee'].pk, 'approve'])
        self.assertEqual(self.client.post(url).status_code, 403)
        self.requests['employee'].refresh_from_db()
        self.assertEqual(self.requests['employee'].status, 'pending')
        self.assertFalse(LeaveDay.objects.exists())

    def test_get_cannot_approve_or_reject(self):
        self.client.force_login(self.people['hr'].user)
        for action in ['approve', 'reject']:
            url = reverse('leaves:review', args=[self.requests['employee'].pk, action])
            self.assertEqual(self.client.get(url).status_code, 405)
        self.requests['employee'].refresh_from_db()
        self.assertEqual(self.requests['employee'].status, 'pending')
        self.assertFalse(LeaveDay.objects.exists())
