from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from nhan_vien.models import NhanVien, PhongBan
from nhan_vien.access import TRUONG_PHONG


class EmployeeDirectoryFiltersTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('directory-admin', password='test-only')
        self.client.force_login(self.user)
        self.department = PhongBan.objects.create(ma_phong_ban='DIR', ten_phong_ban='Directory')
        self.other_department = PhongBan.objects.create(ma_phong_ban='OTHER', ten_phong_ban='Other')
        self.people = []
        for index, (active, hired, department) in enumerate([
            (True, date(2020, 1, 1), self.department),
            (False, date(2021, 1, 1), self.department),
            (True, date(2099, 1, 1), self.other_department),
        ]):
            self.people.append(NhanVien.objects.create(
                nguoi_dung=get_user_model().objects.create_user(f'directory-person-{index}'),
                ma_ho_so=f'DIR{index}', ho_va_ten=f'Person {index}',
                dang_hoat_dong=active, ngay_vao_lam=hired,
                phong_ban=department, luong_co_ban=10000000,
            ))

    def test_total_includes_inactive_and_future_employees_independent_of_date(self):
        for day in ['2010-01-01', '2026-11-17']:
            response = self.client.get(reverse('dashboard'), {'date': day})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['total_employees'], 3)
            self.assertContains(response, f'href="{reverse("employees")}"')
            self.assertNotContains(response, 'active_as_of=')
        self.assertEqual(response.context['attendance_counts']['unchecked'], 1)

    def test_directory_has_only_regular_filters_even_for_old_dashboard_urls(self):
        response = self.client.get(reverse('employees'), {
            'active_as_of': '2010-01-01', 'gioi_tinh': 'Nam',
        })
        self.assertCountEqual(response.context['rows'], self.people)
        self.assertNotContains(response, 'Bỏ lọc từ Dashboard')
        self.assertNotContains(response, 'name="hoat_dong_den_ngay"')

    def test_regular_department_keyword_and_hire_date_filters_still_work(self):
        response = self.client.get(reverse('employees'), {
            'department': self.department.pk, 'q': 'Person',
            'hire_from': '2021-01-01', 'hire_to': '2021-12-31',
        })
        self.assertEqual(list(response.context['rows']), [self.people[1]])

    def test_department_links_use_the_regular_directory_filter(self):
        response = self.client.get(reverse('departments'), {'date': '2026-11-17'})
        self.assertEqual(response.context['total_employees'], 3)
        self.assertContains(response, f'href="{reverse("employees")}?department={self.department.pk}"')
        self.assertNotContains(response, 'active_as_of=')

    def test_invalid_filter_values_show_errors_and_do_not_return_all_employees(self):
        for data in [{'hire_from': '2026-02-30'}, {'department': 'invalid'}, {'status': 'unknown'}]:
            response = self.client.get(reverse('employees'), data)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['filter_form'].errors)
            self.assertFalse(response.context['rows'].exists())

    def test_manager_cannot_expand_scope_with_department_filter(self):
        manager = self.people[0].nguoi_dung
        manager.groups.add(Group.objects.get_or_create(name=TRUONG_PHONG)[0])
        self.department.truong_phong = self.people[0]
        self.department.save()
        self.client.force_login(manager)
        response = self.client.get(reverse('employees'))
        self.assertCountEqual(response.context['rows'], self.people[:2])
        self.assertCountEqual(response.context['departments'], [self.department])
        response = self.client.get(reverse('employees'), {'department': self.other_department.pk})
        self.assertTrue(response.context['filter_form'].errors)
        self.assertFalse(response.context['rows'].exists())

    def test_ordinary_employee_cannot_open_management_directory(self):
        self.client.force_login(self.people[1].nguoi_dung)
        self.assertEqual(self.client.get(reverse('employees')).status_code, 403)
