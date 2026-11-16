from datetime import date, time
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError
from django.test import TestCase, Client

from bang_luong.models import PayrollPeriod
from nhan_vien.access import HR, DIRECTOR, MANAGER
from nhan_vien.models import Department, Employee


class BulkApprovalTests(TestCase):
    def setUp(self):
        self.hr = User.objects.create_user('bulk-hr')
        self.hr.groups.add(Group.objects.create(name=HR))
        self.director = User.objects.create_user('bulk-director')
        self.director.groups.add(Group.objects.create(name=DIRECTOR))
        self.manager = User.objects.create_user('bulk-manager')
        self.manager.groups.add(Group.objects.create(name=MANAGER))
        self.employees = [Employee.objects.create(
            user=User.objects.create_user(f'bulk-employee-{i}'), code=f'BULK{i}',
            full_name=f'Employee {i}', hire_date=date(2020, 1, 1), base_salary=0,
            department=Department.objects.create(code=f'BULK{i}', name=f'Department {i}'),
        ) for i in (1, 2)]
        self.period = PayrollPeriod.objects.create(nam=2026, thang=11)
        self.url = f'/bang_cong/duyet-hang-loat/{self.period.pk}/'
        self.client.force_login(self.hr)

    @patch('bang_cong.views.nhan_su.duyet_cong_nhan_vien')
    def test_selected_employees_are_deduplicated_and_filters_preserved(self, approve):
        approve.return_value = SimpleNamespace(payroll_error='')
        ids = [employee.pk for employee in self.employees]
        response = self.client.post(self.url + '?review=pending&page=2', {'employee_ids': ids + ids})
        self.assertEqual(approve.call_count, 2)
        self.assertEqual({call.args[1].pk for call in approve.call_args_list}, set(ids))
        self.assertIn('month=11', response.url)
        self.assertIn('year=2026', response.url)
        self.assertIn('review=pending', response.url)
        self.assertIn('page=2', response.url)

    @patch('bang_cong.views.nhan_su.duyet_cong_nhan_vien')
    def test_one_failure_does_not_stop_other_employees(self, approve):
        approve.side_effect = [ValidationError('Missing attendance'), SimpleNamespace(payroll_error='Salary error')]
        response = self.client.post(self.url, {'employee_ids': [e.pk for e in self.employees]}, follow=True)
        self.assertEqual(approve.call_count, 2)
        self.assertContains(response, 'Missing attendance')
        self.assertContains(response, 'Salary error')
        self.assertContains(response, 'BULK1')

    @patch('bang_cong.views.nhan_su.duyet_cong_nhan_vien')
    def test_invalid_empty_and_locked_selections_do_not_call_service(self, approve):
        for ids in ([], ['bad'], [999999], [self.employees[0].pk, 999999]):
            self.assertEqual(self.client.post(self.url, {'employee_ids': ids}).status_code, 302)
        self.period.trang_thai = 'approved'
        self.period.save()
        self.client.post(self.url, {'employee_ids': [self.employees[0].pk]})
        approve.assert_not_called()

    @patch('bang_cong.views.nhan_su.duyet_cong_nhan_vien')
    def test_authorization_post_only_and_csrf(self, approve):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        for user in (self.manager, self.employees[0].user):
            self.client.force_login(user)
            self.assertEqual(self.client.post(self.url, {'employee_ids': [self.employees[0].pk]}).status_code, 403)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.hr)
        self.assertEqual(csrf_client.post(self.url, {'employee_ids': [self.employees[0].pk]}).status_code, 403)
        approve.assert_not_called()
        self.client.force_login(self.director)
        approve.return_value = SimpleNamespace(payroll_error='')
        self.assertEqual(self.client.post(self.url, {'employee_ids': [self.employees[0].pk]}).status_code, 302)
        approve.assert_called_once()

    def test_bulk_controls_visibility_and_eligible_rows(self):
        from ..models import ChamCong
        ChamCong.objects.create(nhan_vien=self.employees[0], ngay=date(2026, 11, 10), trang_thai='incomplete')
        url = '/bang_cong/?month=11&year=2026'
        response = self.client.get(url)
        self.assertContains(response, 'id="bulk-approval"')
        self.assertContains(response, f'name="employee_ids" value="{self.employees[0].pk}"')
        self.assertNotContains(response, f'name="employee_ids" value="{self.employees[1].pk}"')
        self.period.trang_thai = 'approved'
        self.period.save()
        self.assertNotContains(self.client.get(url), 'id="bulk-approval"')
        self.client.force_login(self.manager)
        self.assertNotContains(self.client.get(url), 'id="bulk-approval"')

    @patch('bang_luong.services.tinh_toan.cap_nhat_luong_nhan_vien', return_value='')
    def test_real_approval_keeps_success_and_closes_period_after_last_employee(self, salary):
        from ..models import ChamCong, ChotBangCong
        from ..services.cham_cong_service import lich_thang
        days = [day.ngay for day in lich_thang(2026, 11, self.period).values() if day.loai_ngay == 'work']
        self.assertTrue(days)
        def fill(employee):
            ChamCong.objects.bulk_create([ChamCong(
                nhan_vien=employee, ngay=day, gio_vao=time(8), gio_ra=time(17), trang_thai='present',
            ) for day in days])
        fill(self.employees[0])
        ids = [e.pk for e in self.employees]
        self.client.post(self.url, {'employee_ids': ids})
        self.assertEqual(ChotBangCong.objects.filter(tong_hop__ky_cong=self.period).count(), 1)
        self.period.refresh_from_db()
        self.assertEqual(self.period.trang_thai, 'pending')
        fill(self.employees[1])
        self.client.post(self.url, {'employee_ids': ids})
        self.period.refresh_from_db()
        self.assertEqual(self.period.trang_thai, 'approved')
        self.assertEqual(ChotBangCong.objects.filter(tong_hop__ky_cong=self.period).count(), 2)
        self.assertEqual(salary.call_count, 2)
