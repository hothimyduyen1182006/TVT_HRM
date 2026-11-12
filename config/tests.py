from pathlib import Path
from tempfile import TemporaryDirectory
from django.contrib.auth.models import Group
from nhan_vien.models import Education, LaborContract
from nghi_phep.models import LeaveRequest
from datetime import date, time

from django.conf import settings
from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.sessions.models import Session
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import NoReverseMatch, Resolver404, resolve, reverse

from nhan_vien.models import Department, Employee
from nhan_vien import test_personal_records as personal_fixtures
from bang_cong.models import KyCong
from bang_luong.models import PayrollRecord, PayrollPeriod


class HomePageTests(TestCase):
    setUp=personal_fixtures.ManagementPersonalRecordsTests.setUp

    def test_home_requires_login_and_does_not_accept_post(self):
        self.assertRedirects(self.client.get('/'),'/accounts/login/?next=/',fetch_redirect_response=False)
        self.client.force_login(self.people[3].user)
        self.assertEqual(self.client.post('/').status_code,405)

    def test_every_role_has_own_attendance_and_salary_shortcuts(self):
        before=list(PayrollRecord.objects.values())
        for employee in self.people:
            with self.subTest(user=employee.user.username):
                self.client.force_login(employee.user)
                response=self.client.get('/')
                self.assertEqual(response.status_code,200)
                self.assertContains(response,employee.full_name)
                self.assertContains(response,'Chào mừng trở lại!')
                self.assertEqual(response.context['attendance_url'],'/bang_cong/personal/')
                self.assertEqual(response.context['payroll_url'],'/bang_luong/personal/?month=1&year=2026')
                self.assertEqual(self.client.get(response.context['attendance_url']).status_code,200)
                self.assertEqual(self.client.get(response.context['payroll_url']).status_code,200)
                self.assertEqual(response.context['leave_url'],'/nghi_phep/')
        self.assertEqual(list(PayrollRecord.objects.values()),before)

    def test_latest_salary_is_selected_only_for_current_user(self):
        employee=self.people[3]
        for owner,year in [(employee,2027),(self.people[0],2028)]:
            attendance=KyCong.objects.create(nam=year,thang=2,gio_bat_dau=time(8),bat_dau_nghi_trua=time(12),
                ket_thuc_nghi_trua=time(13),gio_ket_thuc=time(17),gio_chuan=8)
            period=PayrollPeriod.objects.create(attendance_period=attendance)
            record=PayrollRecord.objects.get(employee=owner)
            record.pk=None
            record.period=period
            record.save()
        self.client.force_login(employee.user)
        response=self.client.get('/',{'employee':self.people[0].pk,'month':2,'year':2028})
        self.assertEqual(response.context['payroll_url'],'/bang_luong/personal/?month=2&year=2027')
        self.assertContains(response,'Phiếu lương mới nhất · 02/2027')
        self.assertNotContains(response,'02/2028')

    def test_employee_without_salary_has_working_empty_payslip_link(self):
        employee=self.people[3]
        PayrollRecord.objects.filter(employee=employee).delete()
        self.client.force_login(employee.user)
        response=self.client.get('/')
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get(response.context['payroll_url']).status_code,200)

    def test_unlinked_accounts_and_admin_have_no_broken_personal_links(self):
        user=get_user_model().objects.create_user('home-unlinked',first_name='Nguyễn',last_name='Nhi')
        self.client.force_login(user)
        response=self.client.get('/')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['display_name'],'Nguyễn Nhi')
        self.assertEqual(response.context['attendance_url'],'')
        self.assertEqual(response.context['leave_url'],'')
        admin=get_user_model().objects.create_superuser('home-admin',password='TestOnly')
        self.client.force_login(admin)
        response=self.client.get('/')
        self.assertEqual(response.context['attendance_url'],'/bang_cong/')
        self.assertEqual(response.context['payroll_url'],'/bang_luong/')
        self.assertEqual(self.client.get('/dashboard/').status_code,200)

    def test_display_name_is_escaped_and_dashboard_stays_protected(self):
        employee=self.people[3]
        employee.full_name='<script>alert(1)</script>'
        employee.save()
        self.client.force_login(employee.user)
        response=self.client.get('/')
        self.assertContains(response,'&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response,'<script>alert(1)</script>')
        self.assertRedirects(self.client.get('/dashboard/'),'/bang_cong/',fetch_redirect_response=False)


class LoginSessionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.password = 'TestOnly-Session@2026'
        cls.user_a = get_user_model().objects.create_user('session-a', password=cls.password)
        cls.user_b = get_user_model().objects.create_user('session-b', password=cls.password)
        department = Department.objects.create(code='SESSION', name='Phòng kiểm thử')
        for user in [cls.user_a, cls.user_b]:
            Employee.objects.create(user=user, code=user.username, full_name=user.username,
                department=department, hire_date=date(2020, 1, 1), base_salary=10000000)

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.login_url = reverse('login')

    def login(self, user=None, remember=False, **extra):
        self.client.get(self.login_url)
        data = {'username': (user or self.user_a).username, 'password': self.password, **extra}
        if remember:
            data['remember'] = '1'
        return self.client.post(self.login_url, data,
            HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)

    def test_remember_sets_default_age_and_persistent_cookie(self):
        response = self.login(remember=True)
        self.assertRedirects(response, reverse('home'))
        session = self.client.session
        self.assertFalse(session.get_expire_at_browser_close())
        self.assertEqual(session.get_expiry_age(), settings.SESSION_COOKIE_AGE)
        self.assertEqual(int(response.cookies[settings.SESSION_COOKIE_NAME]['max-age']),
                         settings.SESSION_COOKIE_AGE)

    @override_settings(SESSION_COOKIE_AGE=3600)
    def test_remember_respects_configured_age(self):
        self.assertEqual(self.login(remember=True).status_code, 302)
        self.assertEqual(self.client.session.get_expiry_age(), 3600)

    def test_without_remember_expires_when_browser_closes(self):
        response = self.login()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.client.session.get_expire_at_browser_close())
        self.assertEqual(response.cookies[settings.SESSION_COOKIE_NAME]['max-age'], '')
        self.assertEqual(response.cookies[settings.SESSION_COOKIE_NAME]['expires'], '')

    def test_same_user_can_switch_from_browser_session_to_remember(self):
        self.login()
        self.assertTrue(self.client.session.get_expire_at_browser_close())
        self.login(remember=True)
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertEqual(self.client.session.get_expiry_age(), settings.SESSION_COOKIE_AGE)

    def test_same_user_can_switch_from_remember_to_browser_session(self):
        self.login(remember=True)
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.login()
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_account_switch_clears_previous_session_data_and_scope(self):
        self.login(remember=True)
        session = self.client.session
        old_key = session.session_key
        session['clock_success'] = {'record': 123, 'action': 'in'}
        session.save()
        self.login(user=self.user_b)
        session = self.client.session
        self.assertNotEqual(session.session_key, old_key)
        self.assertEqual(session[SESSION_KEY], str(self.user_b.pk))
        self.assertNotIn('clock_success', session)
        self.assertTrue(session.get_expire_at_browser_close())
        response = self.client.get(reverse('personal_profile'))
        self.assertContains(response, self.user_b.username)
        self.assertNotContains(response, self.user_a.username)

    def test_wrong_password_reports_error_without_authenticating(self):
        response = self.login(password='Incorrect-Test-Password')
        self.assertContains(response, 'Đăng nhập thất bại, tài khoản hoặc mật khẩu không đúng')
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_inactive_account_cannot_login(self):
        self.user_b.is_active = False
        self.user_b.save(update_fields=['is_active'])
        response = self.login(user=self.user_b)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_login_requires_csrf(self):
        response = self.client.post(self.login_url,
            {'username': self.user_a.username, 'password': self.password})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_safe_next_redirect_remains_supported(self):
        target = reverse('personal_profile')
        self.assertRedirects(self.login(next=target), target)

    def test_external_next_does_not_override_local_redirect(self):
        self.assertRedirects(self.login(next='https://outside.invalid/'), reverse('home'))

    def test_post_logout_clears_authentication_session_and_old_session_row(self):
        self.login(remember=True)
        session = self.client.session
        old_key = session.session_key
        session['clock_success'] = {'record': 123, 'action': 'out'}
        session.save()
        response = self.client.post(reverse('logout'),
            HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)
        self.assertRedirects(response, self.login_url)
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertNotIn('clock_success', self.client.session)
        self.assertFalse(Session.objects.filter(session_key=old_key).exists())
        self.assertRedirects(self.client.get(reverse('personal_profile')),
            self.login_url + '?next=' + reverse('personal_profile'), fetch_redirect_response=False)

    def test_get_and_head_logout_are_rejected_without_ending_session(self):
        self.login()
        old_key = self.client.session.session_key
        for method in [self.client.get, self.client.head]:
            response = method(reverse('logout'))
            self.assertEqual(response.status_code, 405)
            self.assertEqual(self.client.session[SESSION_KEY], str(self.user_a.pk))
            self.assertEqual(self.client.session.session_key, old_key)

    def test_logout_without_csrf_is_rejected_and_keeps_session(self):
        self.login()
        self.assertEqual(self.client.post(reverse('logout')).status_code, 403)
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user_a.pk))

    def test_logout_options_advertises_post_only(self):
        response = self.client.options(reverse('logout'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response['Allow'].replace(' ', '').split(',')), {'POST', 'OPTIONS'})

    def test_existing_navbar_keeps_logout_form_and_csrf(self):
        self.login()
        response = self.client.get(reverse('home'))
        self.assertContains(response, f'<form method="post" action="{reverse("logout")}">')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, 'Đăng xuất')

    def test_anonymous_post_logout_is_safe_and_returns_to_login(self):
        self.client.get(self.login_url)
        response = self.client.post(reverse('logout'),
            HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)
        self.assertRedirects(response, self.login_url)
        self.assertNotIn(SESSION_KEY, self.client.session)


class PrivateMediaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        department = Department.objects.create(code='MA', name='Phòng A')
        other_department = Department.objects.create(code='MB', name='Phòng B')
        cls.people = {}
        cls.files = {}
        for name, room, role in [
            ('employee', department, 'Nhân viên'),
            ('manager', department, 'Trưởng phòng'),
            ('outsider', other_department, 'Nhân viên'),
        ]:
            user = get_user_model().objects.create_user(name)
            user.groups.add(Group.objects.get_or_create(name=role)[0])
            employee = Employee.objects.create(user=user, code=name, full_name=name,
                department=room, hire_date=date(2020, 1, 1), base_salary=10000000,
                avatar=f'employees/avatars/{name}.png')
            education = Education.objects.create(employee=employee, code=name,
                degree='Đại học', certificate_file=f'employees/education/{name}.pdf')
            contract = LaborContract.objects.create(employee=employee, code=name, number=name,
                contract_type='Có thời hạn', signed_date=date(2026, 1, 1),
                start_date=date(2026, 1, 1), agreed_salary=10000000,
                contract_file=f'employees/contracts/{name}.pdf')
            leave = LeaveRequest.objects.create(employee=employee,
                start_date=date(2026, 1, 5), end_date=date(2026, 1, 5), reason='Khám sức khỏe',
                evidence=f'leave_evidence/2026/01/{name}.png')
            cls.people[name] = employee
            cls.files[name] = [employee.avatar.name, education.certificate_file.name,
                               contract.contract_file.name, leave.evidence.name]
        department.manager = cls.people['manager']
        department.save(update_fields=['manager'])
        cls.reviewers = []
        for role in ['Nhân sự', 'Giám đốc']:
            user = get_user_model().objects.create_user(role)
            user.groups.add(Group.objects.get_or_create(name=role)[0])
            cls.reviewers.append(user)
        cls.unlinked = get_user_model().objects.create_user('unlinked')

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.media_root = Path(temporary.name)
        self.enterContext(override_settings(MEDIA_ROOT=temporary.name))
        for paths in self.files.values():
            for name in paths:
                target = self.media_root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b'private-file-content')

    def url(self, name):
        return reverse('protected-media', kwargs={'path': name})

    def assert_download(self, name):
        response = self.client.get(self.url(name))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'private-file-content')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertTrue(response['Content-Disposition'].startswith(
            'inline' if name.endswith('.png') else 'attachment'))
        response.close()

    def test_anonymous_cannot_use_direct_media_urls(self):
        for name in self.files['employee']:
            response = self.client.get(self.url(name))
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith(reverse('login') + '?next='))

    def test_employee_downloads_own_files_only(self):
        self.client.force_login(self.people['employee'].user)
        for name in self.files['employee']:
            self.assert_download(name)
        for name in self.files['outsider'] + self.files['manager']:
            self.assertEqual(self.client.get(self.url(name)).status_code, 404)

    def test_manager_downloads_only_managed_department_files(self):
        self.client.force_login(self.people['manager'].user)
        for name in self.files['employee'] + self.files['manager']:
            self.assert_download(name)
        for name in self.files['outsider']:
            self.assertEqual(self.client.get(self.url(name)).status_code, 404)

    def test_hr_and_director_retain_company_scope(self):
        for user in self.reviewers:
            self.client.force_login(user)
            for name in self.files['employee'] + self.files['outsider']:
                self.assert_download(name)

    def test_unlinked_user_cannot_download_employee_files(self):
        self.client.force_login(self.unlinked)
        for name in self.files['employee']:
            self.assertEqual(self.client.get(self.url(name)).status_code, 404)

    def test_unknown_files_are_not_served_even_if_present_on_disk(self):
        self.client.force_login(self.reviewers[0])
        (self.media_root / 'unregistered.pdf').write_bytes(b'not-a-managed-document')
        self.assertEqual(self.client.get(self.url('unregistered.pdf')).status_code, 404)

    def test_missing_file_returns_404(self):
        self.client.force_login(self.people['employee'].user)
        name = self.files['employee'][1]
        (self.media_root / name).unlink()
        self.assertEqual(self.client.get(self.url(name)).status_code, 404)

    def test_traversal_is_rejected_even_for_registered_paths(self):
        self.client.force_login(self.reviewers[0])
        for name in ['../db.sqlite3', 'employees/../db.sqlite3',
                     'employees\\..\\db.sqlite3', 'C:/db.sqlite3',
                     'employees//avatars/employee.png', 'employees/./avatars/employee.png']:
            with self.subTest(path=name):
                Employee.objects.filter(pk=self.people['employee'].pk).update(avatar=name)
                self.assertEqual(self.client.get(self.url(name)).status_code, 404)

    def test_encoded_traversal_and_query_parameters_do_not_grant_access(self):
        self.client.force_login(self.people['employee'].user)
        self.assertEqual(self.client.get('/media/%2e%2e/db.sqlite3').status_code, 404)
        self.assertEqual(self.client.get('/media/%252e%252e/db.sqlite3').status_code, 404)
        url = self.url(self.files['outsider'][1]) + f'?employee={self.people["employee"].pk}'
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_debug_mode_never_restores_public_media_fallback(self):
        for debug in [True, False]:
            with self.subTest(debug=debug), override_settings(DEBUG=debug):
                self.client.logout()
                name = self.files['employee'][1]
                self.assertEqual(self.client.get(self.url(name)).status_code, 302)
                self.client.force_login(self.people['employee'].user)
                self.assert_download(name)

    def test_profile_and_leave_template_links_continue_to_work(self):
        self.client.force_login(self.people['employee'].user)
        response = self.client.get(reverse('personal_profile'))
        self.assertEqual(response.status_code, 200)
        for name in self.files['employee'][:3]:
            self.assertContains(response, self.url(name))
        leave = LeaveRequest.objects.get(employee=self.people['employee'])
        response = self.client.get(reverse('nghi_phep:detail', args=[leave.pk]))
        evidence_url = reverse('nghi_phep:evidence', args=[leave.pk])
        self.assertContains(response, evidence_url)
        response = self.client.get(evidence_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'private-file-content')
        response.close()

    def test_head_allowed_and_post_rejected(self):
        self.client.force_login(self.people['employee'].user)
        url = self.url(self.files['employee'][0])
        response = self.client.head(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b''.join(response.streaming_content), b'')
        response.close()
        self.assertEqual(self.client.post(url).status_code, 405)

    def test_evidence_url_checks_authentication_scope_and_cache(self):
        leave = LeaveRequest.objects.get(employee=self.people['outsider'])
        url = reverse('nghi_phep:evidence', args=[leave.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.people['employee'].user)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.people['manager'].user)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.reviewers[0])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        response.close()
        self.assertEqual(self.client.post(url).status_code, 405)

    def test_non_image_upload_cannot_render_active_content_inline(self):
        leave = LeaveRequest.objects.get(employee=self.people['employee'])
        name = 'leave_evidence/2026/01/document.html'
        (self.media_root / name).write_bytes(b'<script>alert(1)</script>')
        leave.evidence = name
        leave.save(update_fields=['evidence'])
        self.client.force_login(self.people['employee'].user)
        for url in [self.url(name), reverse('nghi_phep:evidence', args=[leave.pk])]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response['Content-Disposition'].startswith('attachment'))
            self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
            response.close()


class BangCongURLTests(SimpleTestCase):
    def test_all_attendance_routes_use_new_namespace_and_prefix(self):
        routes = {'list': [], 'personal': [], 'clock': [], 'create': [],
                  'employee-month': [1], 'employee-approve': [1, 2],
                  'history': [1], 'export': [1], 'detail': [1],
                  'edit': [1], 'transition': [2]}
        for name, args in routes.items():
            with self.subTest(route=name):
                url = reverse('bang_cong:' + name, args=args)
                self.assertTrue(url.startswith('/bang_cong/'))
                self.assertEqual(resolve(url).view_name, 'bang_cong:' + name)

    def test_old_public_prefix_and_namespace_are_not_registered(self):
        with self.assertRaises(Resolver404):
            resolve('/attendance/')
        with self.assertRaises(NoReverseMatch):
            reverse('attendance:list')

    def test_all_business_apps_keep_database_identity_with_new_packages(self):
        from django.apps import apps
        names = {'attendance': 'bang_cong', 'employees': 'nhan_vien',
                 'payroll': 'bang_luong', 'leaves': 'nghi_phep', 'bonuses': 'thuong'}
        for label, name in names.items():
            with self.subTest(app=name):
                self.assertEqual(apps.get_app_config(label).name, name)

    def test_other_business_urls_resolve_with_vietnamese_prefixes(self):
        for name in ['bang_luong', 'nghi_phep', 'thuong']:
            with self.subTest(app=name):
                url = reverse(name + ':list')
                self.assertEqual(url, '/' + name + '/')
                self.assertEqual(resolve(url).namespace, name)
        self.assertEqual(reverse('employees'), '/nhan_vien/')
