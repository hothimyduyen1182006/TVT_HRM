from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from nhan_vien.access import GIAM_DOC, NHAN_SU, TRUONG_PHONG
from nhan_vien.models import PhongBan, NhanVien
from .models import LeaveDay, LeaveRequest


class LeaveAccessTests(TestCase):
    """Exercise real views, templates and CSRF using Django's test database."""

    @classmethod
    def setUpTestData(cls):
        cls.department = PhongBan.objects.create(ma_phong_ban='LA', ten_phong_ban='Phòng A')
        cls.other_department = PhongBan.objects.create(ma_phong_ban='LB', ten_phong_ban='Phòng B')
        cls.people = {}
        for name, department, role in [
            ('employee', cls.department, 'Nhân viên'),
            ('teammate', cls.department, 'Nhân viên'),
            ('manager', cls.department, TRUONG_PHONG),
            ('outsider', cls.other_department, 'Nhân viên'),
            ('hr', cls.other_department, NHAN_SU),
            ('director', cls.other_department, GIAM_DOC),
            ('inactive', cls.department, 'Nhân viên'),
        ]:
            user = get_user_model().objects.create_user(username=f'leave-{name}')
            user.groups.add(Group.objects.get_or_create(name=role)[0])
            cls.people[name] = NhanVien.objects.create(
                nguoi_dung=user, ma_ho_so=f'LEAVE-{name}', ho_va_ten=f'Nhân viên {name}',
                phong_ban=department, ngay_vao_lam=date(2020, 1, 1),
                luong_co_ban=10000000, dang_hoat_dong=name != 'inactive',
            )
        cls.department.truong_phong = cls.people['manager']
        cls.department.save(update_fields=['truong_phong'])
        cls.unlinked = get_user_model().objects.create_user(username='leave-unlinked')
        cls.unlinked.groups.add(Group.objects.get(name='Nhân viên'))
        cls.unlinked_hr = get_user_model().objects.create_user(username='leave-unlinked-hr')
        cls.unlinked_hr.groups.add(Group.objects.get(name=NHAN_SU))
        cls.requests = {
            name: LeaveRequest.objects.create(
                employee=employee, Ngay_bat_dau=date(2026, 1, 12),
                Ngay_ket_thuc=date(2026, 1, 12), Ly_do=f'Lý do riêng của {name}',
                Trang_thai='rejected' if name == 'outsider' else 'pending',
            )
            for name, employee in cls.people.items()
        }

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.url = reverse('nghi_phep:list')

    def post(self, url, data=None, **kwargs):
        # The login page provides a real CSRF cookie even without an employee profile.
        self.client.get(reverse('login'))
        token = self.client.cookies['csrftoken'].value
        return self.client.post(url, data or {}, HTTP_X_CSRFTOKEN=token, **kwargs)

    def valid_data(self, **overrides):
        return {
            'Ngay_bat_dau': '2026-01-20', 'Ngay_ket_thuc': '2026-01-20',
            'leave_type': 'annual', 'Ly_do': 'Nghỉ phép theo kế hoạch', 'view': 'mine', **overrides,
        }

    def assert_scope(self, response, names):
        self.assertEqual(response.status_code, 200)
        expected = {self.requests[name].pk for name in names}
        self.assertEqual(set(response.context['requests'].values_list('pk', flat=True)), expected)
        for name, item in self.requests.items():
            if name in names:
                self.assertContains(response, reverse('nghi_phep:detail', args=[item.pk]))
                detail = self.client.get(reverse('nghi_phep:detail', args=[item.pk]))
                self.assertContains(detail, item.Ly_do)
            else:
                self.assertNotContains(response, item.Ly_do)

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
                self.client.force_login(self.people[name].nguoi_dung)
                self.assert_scope(self.client.get(self.url), expected)
                response = self.post(self.url, {'Ly_do': 'Thiếu ngày nghỉ'})
                if not response.context['manage_view']:
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
        self.client.force_login(self.people['inactive'].nguoi_dung)
        self.assert_scope(self.client.get(self.url), set())
        self.assert_scope(self.post(self.url, self.valid_data()), set())
        self.assertEqual(LeaveRequest.objects.count(), len(self.requests))

    def test_unlinked_hr_retains_authorized_review_scope_after_post(self):
        self.client.force_login(self.unlinked_hr)
        self.assert_scope(self.client.get(self.url), set(self.requests))
        self.assert_scope(self.post(self.url, self.valid_data(view='manage')), set(self.requests))
        self.assertEqual(LeaveRequest.objects.count(), len(self.requests))

    def test_forged_and_invalid_filters_do_not_expand_scope(self):
        for user in [self.people['employee'].nguoi_dung, self.people['manager'].nguoi_dung, self.unlinked]:
            self.client.force_login(user)
            with self.subTest(user=user.username):
                url = self.url + f'?department={self.other_department.pk}'
                for response in [self.client.get(url), self.post(url, {'Ly_do': 'Thiếu ngày'})]:
                    self.assertEqual(response.status_code, 200)
                    self.assertFalse(response.context['requests'].exists())
                    self.assertNotContains(response, self.requests['outsider'].Ly_do)
                response = self.post(self.url + '?status=invalid', {'Ly_do': 'Thiếu ngày'})
                self.assertTrue(response.context['filters'].errors)
                self.assertNotContains(response, self.requests['outsider'].Ly_do)

    def test_valid_submission_uses_logged_in_employee_and_pending_status(self):
        for index, name in enumerate(['employee', 'manager', 'hr', 'director']):
            with self.subTest(role=name):
                self.client.force_login(self.people[name].nguoi_dung)
                response = self.post(self.url, self.valid_data(
                    Ngay_bat_dau=f'2026-01-{20 + index}', Ngay_ket_thuc=f'2026-01-{20 + index}',
                    employee=self.people['outsider'].pk, Trang_thai='approved',
                    reviewed_by=self.people['director'].nguoi_dung_id,
                ))
                target = self.url + '?view=mine' if name != 'employee' else self.url
                self.assertRedirects(response, target)
                item = LeaveRequest.objects.get(employee=self.people[name], Ngay_bat_dau=date(2026, 1, 20 + index))
                self.assertEqual(item.Trang_thai, 'pending')
                self.assertIsNone(item.reviewed_by_id)
                self.assertTrue(item.paid)
        self.assertEqual(LeaveRequest.objects.count(), len(self.requests) + 4)
        self.assertFalse(LeaveDay.objects.exists())

    def test_model_validation_failure_preserves_own_scope(self):
        self.client.force_login(self.people['employee'].nguoi_dung)
        response = self.post(self.url, self.valid_data(Ngay_bat_dau='2019-01-02', Ngay_ket_thuc='2019-01-02'))
        self.assert_scope(response, {'employee'})
        self.assertContains(response, 'Ngày nghỉ không được trước ngày vào làm.')
        self.assertEqual(LeaveRequest.objects.count(), len(self.requests))

    def test_management_tab_cannot_submit_a_leave_request(self):
        self.client.force_login(self.people['hr'].nguoi_dung)
        response = self.post(self.url, self.valid_data(view='manage'))
        self.assert_scope(response, set(self.requests))
        self.assertContains(response, 'Hãy chuyển sang tab Đơn nghỉ phép của tôi để gửi đơn.')
        self.assertEqual(LeaveRequest.objects.count(), len(self.requests))

    def test_invalid_filters_return_no_rows_on_get_and_post(self):
        self.client.force_login(self.people['hr'].nguoi_dung)
        url = self.url + '?status=invalid'
        for response in [self.client.get(url), self.post(url, {'view': 'manage'})]:
            self.assertTrue(response.context['filters'].errors)
            self.assertFalse(response.context['requests'].exists())
        self.assertEqual(LeaveRequest.objects.count(), len(self.requests))

    def test_detail_and_review_controls_follow_scope(self):
        for name in ['employee', 'manager', 'hr', 'director']:
            self.client.force_login(self.people[name].nguoi_dung)
            own_url = reverse('nghi_phep:detail', args=[self.requests[name].pk])
            response = self.client.get(own_url)
            self.assertEqual(response.status_code, 200)
            review_url = reverse('nghi_phep:review', args=[self.requests[name].pk, 'approve'])
            self.assertNotContains(response, f'action="{review_url}"')
            if name != 'employee':
                teammate_url = reverse('nghi_phep:detail', args=[self.requests['teammate'].pk])
                teammate_review = reverse('nghi_phep:review', args=[self.requests['teammate'].pk, 'approve'])
                self.assertContains(self.client.get(teammate_url), f'action="{teammate_review}"')
            other_url = reverse('nghi_phep:detail', args=[self.requests['outsider'].pk])
            self.assertEqual(self.client.get(other_url).status_code, 200 if name in ['hr', 'director'] else 404)

    def test_employee_cannot_review_even_own_request(self):
        self.client.force_login(self.people['employee'].nguoi_dung)
        for action in ['approve', 'reject']:
            url = reverse('nghi_phep:review', args=[self.requests['employee'].pk, action])
            self.assertEqual(self.post(url, {'review_note': 'Đã xem xét'}).status_code, 403)
        self.requests['employee'].refresh_from_db()
        self.assertEqual(self.requests['employee'].Trang_thai, 'pending')
        self.assertFalse(LeaveDay.objects.exists())

    def test_reviewers_cannot_approve_or_reject_their_own_request(self):
        for name in ['manager', 'hr', 'director']:
            self.client.force_login(self.people[name].nguoi_dung)
            item = self.requests[name]
            for action in ['approve', 'reject']:
                with self.subTest(role=name, action=action):
                    url = reverse('nghi_phep:review', args=[item.pk, action])
                    self.assertEqual(self.post(url, {'review_note': 'Test'}).status_code, 403)
            item.refresh_from_db()
            self.assertEqual(item.Trang_thai, 'pending')
            self.assertIsNone(item.reviewed_by_id)
        self.assertFalse(LeaveDay.objects.exists())

    def test_manager_cannot_review_another_department_by_direct_url(self):
        self.client.force_login(self.people['manager'].nguoi_dung)
        for action in ['approve', 'reject']:
            url = reverse('nghi_phep:review', args=[self.requests['hr'].pk, action])
            self.assertEqual(self.post(url, {'review_note': 'Đã xem xét'}).status_code, 404)
        self.requests['hr'].refresh_from_db()
        self.assertEqual(self.requests['hr'].Trang_thai, 'pending')
        self.assertFalse(LeaveDay.objects.exists())

    def test_authorized_roles_can_approve_and_create_leave_days(self):
        for index, name in enumerate(['manager', 'hr', 'director']):
            self.client.force_login(self.people[name].nguoi_dung)
            day = date(2026, 1, 21 + index)
            item = LeaveRequest.objects.create(employee=self.people['employee'],
                Ngay_bat_dau=day, Ngay_ket_thuc=day, Ly_do='Nghỉ phép hợp lệ', paid=True)
            url = reverse('nghi_phep:review', args=[item.pk, 'approve'])
            self.assertRedirects(self.post(url), reverse('nghi_phep:detail', args=[item.pk]))
            item.refresh_from_db()
            self.assertEqual(item.Trang_thai, 'approved')
            self.assertEqual(item.reviewed_by_id, self.people[name].nguoi_dung_id)
            self.assertIsNotNone(item.reviewed_at)
            leave = LeaveDay.objects.get(employee=item.employee, date=day)
            self.assertTrue(leave.approved)
            self.assertTrue(leave.paid)

    def test_rejection_requires_reason_and_does_not_create_leave_day(self):
        self.client.force_login(self.people['manager'].nguoi_dung)
        item = self.requests['employee']
        url = reverse('nghi_phep:review', args=[item.pk, 'reject'])
        self.assertRedirects(self.post(url), reverse('nghi_phep:detail', args=[item.pk]))
        item.refresh_from_db()
        self.assertEqual(item.Trang_thai, 'pending')
        self.assertRedirects(self.post(url, {'review_note': 'Cần bàn giao công việc'}),
                             reverse('nghi_phep:detail', args=[item.pk]))
        item.refresh_from_db()
        self.assertEqual(item.Trang_thai, 'rejected')
        self.assertEqual(item.review_note, 'Cần bàn giao công việc')
        self.assertFalse(LeaveDay.objects.exists())

    def test_submission_and_review_require_csrf(self):
        self.client.force_login(self.people['employee'].nguoi_dung)
        self.assertEqual(self.client.post(self.url, self.valid_data()).status_code, 403)
        self.assertEqual(LeaveRequest.objects.count(), len(self.requests))
        self.client.force_login(self.people['hr'].nguoi_dung)
        url = reverse('nghi_phep:review', args=[self.requests['employee'].pk, 'approve'])
        self.assertEqual(self.client.post(url).status_code, 403)
        self.requests['employee'].refresh_from_db()
        self.assertEqual(self.requests['employee'].Trang_thai, 'pending')
        self.assertFalse(LeaveDay.objects.exists())

    def test_get_cannot_approve_or_reject(self):
        self.client.force_login(self.people['hr'].nguoi_dung)
        for action in ['approve', 'reject']:
            url = reverse('nghi_phep:review', args=[self.requests['employee'].pk, action])
            self.assertEqual(self.client.get(url).status_code, 405)
        self.requests['employee'].refresh_from_db()
        self.assertEqual(self.requests['employee'].Trang_thai, 'pending')
        self.assertFalse(LeaveDay.objects.exists())
