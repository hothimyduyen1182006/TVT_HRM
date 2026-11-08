import json
from datetime import date, time
from decimal import Decimal
from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import TestCase, Client
from django.utils import timezone
from employees.models import Employee, Department
from attendance.models import AttendancePeriod, AttendanceRecord, WorkCalendarDay, OvertimeApproval
from attendance.services.workflow import change_period
from bonuses.models import Bonus
from .models import PayrollPeriod, PayrollInput, PayrollRecord, PayrollExportLog, PayrollAdjustment, PayrollAuditLog
from .services.calculations import calculate_payroll
from .services.workflow import change_payroll, approve_record


class PayrollTests(TestCase):
    def setUp(self):
        self.hr = User.objects.create_user('hr')
        self.hr.groups.add(Group.objects.get_or_create(name='Nhân sự')[0])
        self.director = User.objects.create_user('director')
        self.director.groups.add(Group.objects.get_or_create(name='Giám đốc')[0])
        self.user = User.objects.create_user('employee')
        self.other_user = User.objects.create_user('other')
        self.dep = Department.objects.create(code='A', name='Phòng A')
        self.other_dep = Department.objects.create(code='B', name='Phòng B')
        self.emp = Employee.objects.create(code='NV01', full_name='Nhân viên 1', user=self.user,
                  department=self.dep, hire_date=date(2020, 1, 1), base_salary=Decimal('8000000'))
        self.other = Employee.objects.create(code='NV02', full_name='Nhân viên 2', user=self.other_user,
                  department=self.other_dep, hire_date=date(2020, 1, 1), base_salary=Decimal('8000000'))
        self.attendance = AttendancePeriod.objects.create(month=1, year=2026, start_time=time(8),
                   lunch_start=time(12), lunch_end=time(13), end_time=time(17), standard_hours=8,
                   policy_confirmed=True, status='approved', employee_ids=[self.emp.pk, self.other.pk])
        WorkCalendarDay.objects.create(date=date(2026, 1, 5), kind='work', expected_units=1)
        self.period = PayrollPeriod.objects.create(attendance_period=self.attendance)
        for employee in [self.emp, self.other]:
            AttendanceRecord.objects.create(employee=employee, date=date(2026, 1, 5), status='present',
                         check_in=time(8), check_out=time(17), work_hours=8, actual_units=1, paid_units=1)
            PayrollInput.objects.create(period=self.period, employee=employee, insurance_base=8000000,
                         insurance_rates={'BH': '0.1'}, tax_amount=100000, tax_basis='Chính sách kỳ thử',
                         insurance_basis='Chỉ là dữ liệu test', verified=True)

    def calculate(self):
        calculate_payroll(self.hr, self.period.pk, 'Tính thử')
        return PayrollRecord.objects.get(period=self.period, employee=self.emp)

    def approve(self):
        change_payroll(self.director, self.period.pk, 'approve', 'Đã kiểm tra')

    def test_exact_net_and_approved_sources(self):
        OvertimeApproval.objects.create(employee=self.emp, date=date(2026, 1, 5), hours=2,
            multiplier=Decimal('1.5'), approved=True, approved_by=self.director, approved_at=timezone.now())
        OvertimeApproval.objects.create(employee=self.other, date=date(2026, 1, 5), hours=2,
            multiplier=Decimal('1.5'), approved=False)
        for approved in [False, True]:
            Bonus.objects.create(employee=self.emp, month=1, year=2026, name='Thưởng', amount=200000,
                reason='Đề xuất thưởng hợp lệ', proposed_by=self.hr, proposed_at=timezone.now(),
                status='approved' if approved else 'pending', approved_by=self.director if approved else None,
                approved_at=timezone.now() if approved else None)
        PayrollAdjustment.objects.create(employee=self.emp, period=self.period, name='Ăn trưa',
                                         kind='allowance', amount=300000, basis='Test', approved=True)
        PayrollAdjustment.objects.create(employee=self.emp, period=self.period, name='Chưa duyệt',
                                         kind='deduction', amount=900000, basis='Test', approved=False)
        row = self.calculate()
        self.assertEqual(row.net_pay, Decimal('10600000'))
        self.assertEqual(row.bonus_pay, 200000)
        self.assertEqual(row.ot_hours, 2)
        self.assertEqual(PayrollRecord.objects.get(employee=self.other).ot_pay, 0)

    def test_no_payroll_before_attendance_approval(self):
        self.attendance.status = 'pending'
        self.attendance.save()
        with self.assertRaises(ValidationError):
            self.calculate()

    def test_missing_tax_data_is_not_zero(self):
        PayrollInput.objects.filter(employee=self.emp).delete()
        with self.assertRaises(ValidationError):
            self.calculate()
        self.assertEqual(PayrollRecord.objects.count(), 0)
        self.assertEqual(PayrollAuditLog.objects.count(), 0)

    def test_zero_standard_safe(self):
        WorkCalendarDay.objects.all().update(expected_units=0)
        with self.assertRaises(ValidationError):
            self.calculate()

    def test_final_rounding(self):
        self.emp.base_salary = Decimal('8000000.60')
        self.emp.save()
        self.assertEqual(self.calculate().net_pay, Decimal('7100001'))

    def test_snapshot_survives_salary_change(self):
        row = self.calculate()
        self.approve()
        self.emp.base_salary = Decimal('90000000')
        self.emp.full_name = 'Tên mới'
        self.emp.save()
        row.refresh_from_db()
        self.assertEqual(row.base_salary, Decimal('8000000'))
        self.assertEqual(row.employee_name, 'Nhân viên 1')
        self.assertEqual(row.net_pay, Decimal('7100000'))

    def test_cannot_recalculate_approved(self):
        self.calculate()
        self.approve()
        with self.assertRaises(ValidationError):
            self.calculate()

    def test_hr_cannot_approve(self):
        self.calculate()
        with self.assertRaises(PermissionDenied):
            change_payroll(self.hr, self.period.pk, 'approve', 'Không đủ quyền')

    def test_payment_requires_evidence(self):
        self.calculate()
        self.approve()
        with self.assertRaises(ValidationError):
            change_payroll(self.director, self.period.pk, 'paid', 'Chi trả')
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'approved')
        change_payroll(self.director, self.period.pk, 'paid', 'Chi trả', 'Giao dịch TEST-001')
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'paid')
        with self.assertRaises(ValidationError):
            change_payroll(self.director, self.period.pk, 'reopen', 'Không mở kỳ đã trả')

    def test_reopen_without_data_change_does_not_require_recalculation(self):
        self.calculate()
        self.approve()
        change_payroll(self.director, self.period.pk, 'reopen', 'Sửa sai')
        self.approve()

    def test_cannot_reopen_attendance_with_approved_payroll(self):
        self.calculate()
        self.approve()
        with self.assertRaises(ValidationError):
            change_period(self.director, self.attendance.pk, 'reopen', 'Chưa mở lương')

    def test_payroll_visibility_and_filters(self):
        own = self.calculate()
        other = PayrollRecord.objects.get(employee=self.other)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(f'/payroll/{own.pk}/').status_code, 200)
        self.assertEqual(self.client.get(f'/payroll/{other.pk}/').status_code, 404)
        response = self.client.get('/payroll/?month=1&year=2026')
        self.assertContains(response, 'NV01')
        self.assertNotContains(response, 'NV02')
        response = self.client.get(f'/payroll/?month=1&year=2026&employee={self.other.pk}')
        self.assertTrue(response.context['form'].errors)

    def test_manager_payroll_scope(self):
        self.calculate()
        self.user.groups.add(Group.objects.get_or_create(name='Trưởng phòng')[0])
        self.dep.manager = self.emp
        self.dep.save()
        self.client.force_login(self.user)
        other = PayrollRecord.objects.get(employee=self.other)
        self.assertEqual(self.client.get(f'/payroll/{other.pk}/').status_code, 404)

    def test_exports_require_approval_and_role(self):
        self.calculate()
        self.client.force_login(self.hr)
        for fmt in ['csv', 'json', 'txt']:
            self.assertEqual(self.client.post(f'/payroll/export/{fmt}/', {'month': 1, 'year': 2026}).status_code, 302)
        self.assertEqual(PayrollExportLog.objects.count(), 0)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post('/payroll/export/json/', {'month': 1, 'year': 2026}).status_code, 403)

    def test_export_all_formats_and_scope(self):
        row = self.calculate()
        self.approve()
        self.client.force_login(self.hr)
        for fmt in ['csv', 'json', 'txt']:
            response = self.client.post(f'/payroll/export/{fmt}/', {'month': 1, 'year': 2026, 'employee': self.emp.pk})
            self.assertEqual(response.status_code, 200)
            text = response.content.decode('utf-8-sig')
            self.assertIn('NV01', text)
            self.assertNotIn('NV02', text)
            self.assertIn('7100000', text)
            if fmt == 'json':
                self.assertEqual(Decimal(json.loads(text)[0]['net_pay']), row.net_pay)
        self.assertEqual(PayrollExportLog.objects.count(), 3)
        self.assertEqual(self.client.get('/payroll/export/csv/').status_code, 405)

    def test_export_rejects_forged_filter(self):
        self.calculate()
        self.approve()
        self.client.force_login(self.hr)
        self.assertEqual(self.client.post('/payroll/export/json/', {'month': 1, 'year': 2026, 'employee': 99999}).status_code, 400)

    def test_csrf_and_post_only(self):
        self.client.force_login(self.director)
        self.assertEqual(self.client.get(f'/payroll/period/{self.period.pk}/').status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.director)
        self.assertEqual(client.post(f'/payroll/period/{self.period.pk}/', {'action': 'approve', 'reason': 'Test'}).status_code, 403)

    def test_inputs_pages_and_invalidate_calculation(self):
        self.calculate()
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get('/payroll/inputs/').status_code, 200)
        obj = PayrollInput.objects.get(employee=self.emp)
        response = self.client.post(f'/payroll/inputs/tax/{obj.pk}/', {
            'insurance_base': '8000000', 'insurance_rates': '{"BH": "0.1"}', 'insurance_basis': 'Đã kiểm tra',
            'tax_amount': '200000', 'tax_basis': 'Căn cứ điều chỉnh', 'verified': 'on'})
        self.assertEqual(response.status_code, 302)
        with self.assertRaises(ValidationError):
            self.approve()
        self.assertEqual(self.calculate().net_pay, Decimal('7000000'))
        self.approve()
        self.assertEqual(self.client.post(f'/payroll/inputs/tax/{obj.pk}/', {}).status_code, 200)
        obj.refresh_from_db()
        self.assertEqual(obj.tax_amount, 200000)

    def test_admin_cannot_bypass_employee_scope(self):
        self.calculate()
        self.user.is_staff = True
        self.user.save()
        from django.contrib.auth.models import Permission
        self.user.user_permissions.add(Permission.objects.get(codename='view_payrollrecord'))
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/admin/payroll/payrollrecord/').status_code, 302)

    def test_generated_records_readonly_in_admin(self):
        self.calculate()
        root = User.objects.create_superuser('root', 'root@example.test', 'test-password-only')
        self.client.force_login(root)
        row = PayrollRecord.objects.get(employee=self.emp)
        self.assertEqual(self.client.post(f'/admin/payroll/payrollrecord/{row.pk}/change/', {'net_pay': 1}).status_code, 403)

    def test_tax_rates_validation(self):
        obj = PayrollInput.objects.get(employee=self.emp)
        obj.insurance_rates = {'invalid': 'NaN'}
        with self.assertRaises(ValidationError):
            obj.full_clean()

    def test_explicit_insurance_tax_exemption(self):
        obj = PayrollInput.objects.get(employee=self.emp)
        obj.insurance_rates = {}
        obj.insurance_base = 0
        obj.tax_amount = 0
        obj.insurance_basis = 'Không thuộc đối tượng tham gia theo dữ liệu kiểm thử'
        obj.tax_basis = 'Không phát sinh thuế theo dữ liệu kiểm thử'
        obj.full_clean()
        obj.save()
        self.assertEqual(self.calculate().net_pay, Decimal('8000000'))

    def test_management_empty_keeps_header_filters_and_actions(self):
        self.client.force_login(self.hr)
        before = (PayrollRecord.objects.count(), PayrollPeriod.objects.count(), PayrollAuditLog.objects.count())
        response = self.client.get('/payroll/', {'month': 10, 'year': 2026})
        self.assertContains(response, 'BẢNG LƯƠNG CHÍNH')
        self.assertContains(response, 'CHƯA CÓ DỮ LIỆU BẢNG LƯƠNG')
        self.assertContains(response, 'Tháng 10/2026')
        for label in ['Tính lương', 'Điều chỉnh', 'Xuất bảng lương', 'Lương thực']:
            self.assertContains(response, label)
        self.assertEqual(before, (PayrollRecord.objects.count(), PayrollPeriod.objects.count(), PayrollAuditLog.objects.count()))

    def test_management_search_and_status_use_saved_data(self):
        self.calculate()
        self.client.force_login(self.hr)
        for query in ['NV01', 'Nhân viên 1']:
            response = self.client.get('/payroll/', {'month': 1, 'year': 2026, 'q': query})
            self.assertEqual(response.context['rows'].count(), 1)
            self.assertContains(response, '7,100,000')
            self.assertNotContains(response, 'NV02')
        response = self.client.get('/payroll/', {'month': 1, 'year': 2026, 'status': 'approved'})
        self.assertContains(response, 'CHƯA CÓ DỮ LIỆU BẢNG LƯƠNG')
        response = self.client.get('/payroll/', {'month': 1, 'year': 2026, 'department': self.dep.pk, 'status': 'pending'})
        self.assertEqual(response.context['rows'].count(), 1)
        self.assertEqual(response.context['form'].cleaned_data['department'], self.dep)

    def test_personal_approved_layout_and_amounts(self):
        own = self.calculate()
        self.approve()
        self.client.force_login(self.user)
        response = self.client.get('/payroll/', {'month': 1, 'year': 2026})
        for text in ['PHIẾU LƯƠNG CÁ NHÂN', 'PHIẾU THANH TOÁN LƯƠNG', 'KHOẢN THU NHẬP',
                     'KHOẢN KHẤU TRỪ', '7,100,000 VNĐ', 'In phiếu lương']:
            self.assertContains(response, text)
        for text in ['BẢNG LƯƠNG CHÍNH', 'data-open-dialog', 'Xuất bảng lương', 'NV02']:
            self.assertNotContains(response, text)
        self.assertEqual(response.context['row'].net_pay, own.net_pay)
        self.assertEqual(response.context['income_total'], Decimal('8000000'))
        self.assertEqual(response.context['deductions_total'], Decimal('900000'))
        self.assertEqual(response.context['metrics']['actual'], Decimal('1'))

    def test_personal_empty_and_invalid_filter_do_not_write(self):
        self.client.force_login(self.user)
        response = self.client.get('/payroll/', {'month': 10, 'year': 2026})
        self.assertContains(response, 'CHƯA CÓ DỮ LIỆU PHIẾU LƯƠNG')
        self.assertContains(response, 'Tháng 10/2026')
        self.assertNotContains(response, 'data-print-payslip')
        self.assertEqual(PayrollRecord.objects.count(), 0)
        self.assertEqual(PayrollAuditLog.objects.count(), 0)
        response = self.client.get('/payroll/', {'month': 13, 'year': 2026})
        self.assertTrue(response.context['form'].errors)
        self.assertIsNone(response.context['row'])

    def test_personal_rejects_foreign_filters_and_management_routes(self):
        row = self.calculate()
        self.client.force_login(self.user)
        response = self.client.get('/payroll/personal/', {'month': 1, 'year': 2026, 'employee': self.other.pk})
        self.assertTrue(response.context['form'].errors)
        self.assertIsNone(response.context['row'])
        self.assertEqual(self.client.get('/payroll/inputs/').status_code, 403)
        self.assertEqual(self.client.post(f'/payroll/period/{self.period.pk}/', {'action': 'calculate', 'reason': 'Sai quyền'}).status_code, 403)

    def test_no_automatic_payment_on_personal_view(self):
        row = self.calculate()
        self.approve()
        self.client.force_login(self.user)
        self.client.get('/payroll/', {'month': 1, 'year': 2026})
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'approved')
        self.assertIsNone(self.period.paid_at)
        response = self.client.get(f'/payroll/{row.pk}/')
        self.assertContains(response, 'Đã duyệt · Chưa chi trả')

    def test_export_matches_new_keyword_and_status_filters(self):
        self.calculate()
        self.approve()
        self.client.force_login(self.hr)
        response = self.client.post('/payroll/export/json/', {'month': 1, 'year': 2026, 'q': 'NV01', 'status': 'approved'})
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]['employee_code'], 'NV01')
        self.assertEqual(PayrollExportLog.objects.get().scope['q'], 'NV01')

    def test_print_assets_and_single_inherited_navbar(self):
        self.calculate()
        self.approve()
        self.client.force_login(self.user)
        response = self.client.get('/payroll/', {'month': 1, 'year': 2026})
        self.assertContains(response, 'aria-label="Điều hướng chính"', count=1)
        self.assertContains(response, 'payroll/payroll.css')
        self.assertContains(response, 'payroll/payroll.js')
        self.assertContains(response, 'id="payroll-slip"', count=1)
        from django.contrib.staticfiles import finders
        from pathlib import Path
        css = Path(finders.find('payroll/payroll.css')).read_text(encoding='utf-8')
        self.assertIn('@media print', css)
        self.assertIn('size: A4', css)
        js = Path(finders.find('payroll/payroll.js')).read_text(encoding='utf-8')
        self.assertIn('window.print()', js)

    def test_salary_components_are_not_reclassified_or_recomputed(self):
        PayrollAdjustment.objects.create(period=self.period, employee=self.emp, name='Khoản đã duyệt',
            kind='deduction', amount=150000, basis='Căn cứ kiểm thử', approved=True)
        row = self.calculate()
        self.approve()
        self.emp.base_salary = 99000000
        self.emp.save()
        self.client.force_login(self.user)
        response = self.client.get('/payroll/', {'month': 1, 'year': 2026})
        self.assertEqual(response.context['row'].base_salary, row.base_salary)
        self.assertContains(response, '6,950,000 VNĐ')
        self.assertContains(response, 'Chưa có khoản phạt tách riêng')
        self.assertEqual(response.context['deductions_total'], Decimal('1050000'))

    def test_pending_visibility_preserves_existing_rule(self):
        # Chờ nhóm xác nhận mâu thuẫn UC-7.1/ảnh: không tự thay quyền xem bản chờ duyệt.
        row = self.calculate()
        self.client.force_login(self.user)
        response = self.client.get('/payroll/', {'month': 1, 'year': 2026})
        self.assertEqual(response.context['row'].pk, row.pk)
        self.assertContains(response, 'Bản chờ duyệt')
        self.assertContains(response, 'Chờ duyệt · Chưa chi trả')

    def test_adjustment_page_respects_selected_period(self):
        self.client.force_login(self.hr)
        response = self.client.get('/payroll/inputs/', {'month': 1, 'year': 2026})
        self.assertEqual(response.context['inputs'].count(), 2)
        response = self.client.get('/payroll/inputs/', {'month': 10, 'year': 2026})
        self.assertEqual(response.context['inputs'].count(), 0)

    def test_director_approves_only_one_employee(self):
        row = self.calculate()
        other = PayrollRecord.objects.get(employee=self.other)
        self.client.force_login(self.director)
        response = self.client.get('/payroll/?month=1&year=2026')
        self.assertContains(response, f'action="/payroll/{row.pk}/approve/"')
        response = self.client.post(f'/payroll/{row.pk}/approve/', follow=True)
        self.assertContains(response, 'Đã duyệt bảng lương của')
        row.refresh_from_db()
        other.refresh_from_db()
        self.period.refresh_from_db()
        self.assertEqual(row.status, 'approved')
        self.assertEqual(row.approved_by, self.director)
        self.assertIsNotNone(row.approved_at)
        self.assertEqual(other.status, 'pending')
        self.assertEqual(self.period.status, 'pending')
        self.assertNotContains(response, f'action="/payroll/{row.pk}/approve/"')
        self.assertContains(response, f'action="/payroll/{other.pk}/approve/"')
        approve_record(self.director, other.pk)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'approved')
        self.assertIsNone(self.period.paid_at)

    def test_employee_payroll_approval_permissions_and_validation(self):
        row = self.calculate()
        url = f'/payroll/{row.pk}/approve/'
        for user in [self.hr, self.user]:
            self.client.force_login(user)
            self.assertEqual(self.client.post(url).status_code, 403)
            response = self.client.get('/payroll/?month=1&year=2026')
            self.assertNotContains(response, f'action="{url}"')
        self.client.force_login(self.director)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.period.attendance_revision = 0
        self.period.save()
        approve_record(self.director, row.pk)
        with self.assertRaises(ValidationError):
            approve_record(self.director, row.pk)

    def test_recalculation_preserves_approved_employee(self):
        row = self.calculate()
        original_id, original_net = row.pk, row.net_pay
        approve_record(self.director, row.pk)
        self.emp.base_salary = 99000000
        self.emp.save()
        self.other.base_salary = 9000000
        self.other.save()
        recalculated = self.calculate()
        self.assertEqual(recalculated.pk, original_id)
        self.assertEqual(recalculated.net_pay, original_net)
        self.assertEqual(recalculated.status, 'approved')
        self.assertEqual(PayrollRecord.objects.get(employee=self.other).base_salary, 9000000)
        self.assertEqual(PayrollRecord.objects.count(), 2)

    def test_individual_approval_locks_inputs_and_attendance(self):
        row = self.calculate()
        approve_record(self.director, row.pk)
        inputs = PayrollInput.objects.get(employee=self.emp)
        with self.assertRaises(ValidationError):
            inputs.full_clean()
        adjustment = PayrollAdjustment(period=self.period, employee=self.emp, name='Sửa trái phép',
            kind='deduction', amount=100, basis='Test', approved=True)
        with self.assertRaises(ValidationError):
            adjustment.full_clean()
        PayrollInput.objects.get(employee=self.other).full_clean()
        with self.assertRaises(ValidationError):
            change_period(self.director, self.attendance.pk, 'reopen', 'Không vượt phiếu lương đã duyệt')

    def test_export_and_personal_status_follow_individual_record(self):
        row = self.calculate()
        approve_record(self.director, row.pk)
        self.client.force_login(self.hr)
        response = self.client.post('/payroll/export/json/', {'month': 1, 'year': 2026, 'status': 'approved'})
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]['employee_code'], self.emp.code)
        self.client.force_login(self.user)
        response = self.client.get('/payroll/?month=1&year=2026')
        self.assertContains(response, 'Đã duyệt · Chưa chi trả')
        self.assertNotContains(response, 'Bản chờ duyệt')

    def test_partial_approval_can_be_reopened_with_audit(self):
        row = self.calculate()
        approve_record(self.director, row.pk)
        change_payroll(self.director, self.period.pk, 'reopen', 'Cần điều chỉnh phiếu đã duyệt')
        row.refresh_from_db()
        self.assertEqual(row.status, 'pending')
        self.assertIsNone(row.approved_at)
        self.assertTrue(PayrollAuditLog.objects.filter(action='approve_employee', actor=self.director).exists())

    def test_individual_attendance_approval_does_not_require_whole_month(self):
        from attendance.models import EmployeeAttendanceApproval
        self.attendance.status = 'pending'
        self.attendance.employee_ids = []
        self.attendance.save()
        EmployeeAttendanceApproval.objects.create(period=self.attendance, employee=self.emp, approved_by=self.hr)
        row = self.calculate()
        self.assertEqual(PayrollRecord.objects.count(), 1)
        approve_record(self.director, row.pk)
        row.refresh_from_db()
        self.period.refresh_from_db()
        self.assertEqual(row.status, 'approved')
        self.assertEqual(self.period.status, 'pending')
        self.assertEqual(self.attendance.status, 'pending')

    def test_recalculation_after_reapproval_uses_new_revision(self):
        from attendance.models import EmployeeAttendanceApproval
        old = self.calculate()
        self.attendance.status = 'pending'
        self.attendance.revision += 1
        self.attendance.save()
        EmployeeAttendanceApproval.objects.create(period=self.attendance, employee=self.emp, approved_by=self.hr)
        changed = AttendanceRecord.objects.get(employee=self.emp)
        changed.paid_units = Decimal('.5')
        changed.save()
        with self.assertRaisesMessage(ValidationError, 'Dữ liệu dùng tính lương đã thay đổi'):
            approve_record(self.director, old.pk)
        fresh = self.calculate()
        self.assertEqual(fresh.breakdown['attendance_revision'], self.attendance.revision)
        approve_record(self.director, fresh.pk)
        other = PayrollRecord.objects.get(employee=self.other)
        self.assertEqual(other.status, 'pending')
        with self.assertRaisesMessage(ValidationError, 'nhân viên này chưa được duyệt'):
            approve_record(self.director, other.pk)
        EmployeeAttendanceApproval.objects.create(period=self.attendance, employee=self.other, approved_by=self.hr)
        approve_record(self.director, other.pk)

    def test_reapproval_timestamp_and_revision_alone_do_not_block(self):
        from attendance.models import EmployeeAttendanceApproval
        row = self.calculate()
        original_time, original_net = row.calculated_at, row.net_pay
        self.attendance.status = 'pending'
        self.attendance.revision += 1
        self.attendance.save()
        EmployeeAttendanceApproval.objects.create(period=self.attendance, employee=self.emp, approved_by=self.hr)
        approve_record(self.director, row.pk)
        row.refresh_from_db()
        self.assertEqual(row.status, 'approved')
        self.assertEqual(row.calculated_at, original_time)
        self.assertEqual(row.net_pay, original_net)

    def test_legacy_snapshot_can_be_approved_when_current_values_match(self):
        from attendance.models import EmployeeAttendanceApproval
        row = self.calculate()
        row.breakdown.pop('source_data')
        row.save(update_fields=['breakdown'])
        self.attendance.revision += 1
        self.attendance.save()
        EmployeeAttendanceApproval.objects.create(period=self.attendance, employee=self.emp, approved_by=self.hr)
        approve_record(self.director, row.pk)
        row.refresh_from_db()
        self.assertEqual(row.status, 'approved')

    def test_real_salary_tax_bonus_and_ot_changes_require_recalculation(self):
        row = self.calculate()
        self.emp.base_salary += 100000
        self.emp.save()
        with self.assertRaises(ValidationError):
            approve_record(self.director, row.pk)
        self.emp.base_salary -= 100000
        self.emp.save()
        inputs = PayrollInput.objects.get(employee=self.emp)
        inputs.tax_amount += 1000
        inputs.save()
        with self.assertRaises(ValidationError):
            approve_record(self.director, row.pk)
        inputs.tax_amount -= 1000
        inputs.save()
        bonus = Bonus.objects.create(employee=self.emp, month=1, year=2026, name='Mới duyệt', amount=100000,
            reason='Đề xuất thưởng hợp lệ', proposed_by=self.hr, proposed_at=timezone.now(),
            status='approved', approved_by=self.director, approved_at=timezone.now())
        with self.assertRaises(ValidationError):
            approve_record(self.director, row.pk)
        bonus.delete()
        OvertimeApproval.objects.create(employee=self.emp, date=date(2026, 1, 5), hours=1,
            multiplier=Decimal('1.5'), approved=True, approved_by=self.director, approved_at=timezone.now())
        with self.assertRaises(ValidationError):
            approve_record(self.director, row.pk)

    def test_incomplete_legacy_bonus_is_not_added_to_payroll(self):
        Bonus.objects.create(employee=self.emp, month=1, year=2026, name='', amount=300000,
            status='approved', approved_by=self.director, approved_at=timezone.now())

        row = self.calculate()

        self.assertEqual(row.bonus_pay, 0)
        self.assertEqual(row.breakdown['bonuses'], [])

    def test_note_or_other_employee_changes_do_not_block_approval(self):
        row = self.calculate()
        AttendanceRecord.objects.filter(employee=self.emp).update(note='Chỉ sửa ghi chú')
        self.other.base_salary += 500000
        self.other.save()
        approve_record(self.director, row.pk)
        row.refresh_from_db()
        self.assertEqual(row.status, 'approved')

    def test_source_check_does_not_modify_money_or_audit(self):
        from .services.workflow import record_approval_error
        row = self.calculate()
        before = (row.net_pay, row.calculated_at, PayrollAuditLog.objects.count())
        self.assertEqual(record_approval_error(row), '')
        self.client.force_login(self.director)
        self.client.get('/payroll/?month=1&year=2026')
        row.refresh_from_db()
        self.assertEqual((row.net_pay, row.calculated_at, PayrollAuditLog.objects.count()), before)

    def insurance_form_data(self):
        return {'insurance_base': '8000000', 'insurance_basis': 'Căn cứ kỳ kiểm thử',
            'tax_amount': '100000', 'tax_basis': 'Căn cứ thuế kiểm thử', 'verified': 'on',
            'insurance-TOTAL_FORMS': '2', 'insurance-INITIAL_FORMS': '1',
            'insurance-MIN_NUM_FORMS': '0', 'insurance-MAX_NUM_FORMS': '20',
            'insurance-0-name': 'BHXH', 'insurance-0-percent': '8',
            'insurance-1-name': 'BHYT', 'insurance-1-percent': '1.5'}

    def test_input_dashboard_shows_missing_and_selected_month(self):
        PayrollInput.objects.filter(employee=self.other).delete()
        self.client.force_login(self.hr)
        response = self.client.get('/payroll/inputs/?month=1&year=2026')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['counts']['missing'], 1)
        self.assertContains(response, 'Bổ sung dữ liệu')
        self.assertContains(response, f'period={self.period.pk}&amp;employee={self.other.pk}')
        response = self.client.get('/payroll/inputs/?month=1&year=2026&readiness=missing')
        self.assertEqual(len(response.context['employee_rows']), 1)
        self.assertEqual(response.context['employee_rows'][0]['employee'], self.other)
        response = self.client.get('/payroll/inputs/?month=10&year=2026')
        self.assertContains(response, 'CHƯA CÓ KỲ LƯƠNG 10/2026')

    def test_insurance_percentage_form_stores_decimal_rates(self):
        obj = PayrollInput.objects.get(employee=self.emp)
        self.client.force_login(self.hr)
        response = self.client.post(f'/payroll/inputs/tax/{obj.pk}/', self.insurance_form_data())
        self.assertEqual(response.status_code, 302)
        self.assertIn('month=1', response.url)
        obj.refresh_from_db()
        self.assertEqual(obj.insurance_rates, {'BHXH': '0.08', 'BHYT': '0.015'})
        self.assertEqual(PayrollAuditLog.objects.get().snapshot[0]['before']['insurance_rates'], {'BH': '0.1'})

    def test_rate_form_rejects_duplicates_and_invalid_percent(self):
        obj = PayrollInput.objects.get(employee=self.emp)
        self.client.force_login(self.hr)
        data = self.insurance_form_data()
        data['insurance-1-name'] = 'bhxh'
        response = self.client.post(f'/payroll/inputs/tax/{obj.pk}/', data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mỗi loại bảo hiểm chỉ được nhập một lần')
        data['insurance-1-name'] = 'BHYT'
        data['insurance-1-percent'] = '105'
        response = self.client.post(f'/payroll/inputs/tax/{obj.pk}/', data)
        self.assertTrue(response.context['form'].rate_formset.errors)
        obj.refresh_from_db()
        self.assertEqual(obj.insurance_rates, {'BH': '0.1'})

    def test_noop_input_save_does_not_add_history(self):
        from .services.inputs import save_input
        obj = PayrollInput.objects.get(employee=self.emp)
        _, changed = save_input(self.hr, obj)
        self.assertFalse(changed)
        self.assertEqual(PayrollAuditLog.objects.count(), 0)

    def test_prefilled_creation_preserves_employee_and_period(self):
        PayrollInput.objects.filter(employee=self.other).delete()
        self.client.force_login(self.hr)
        url = f'/payroll/inputs/tax/new/?period={self.period.pk}&employee={self.other.pk}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].fields['employee'].disabled)
        self.assertTrue(response.context['form'].fields['period'].disabled)
        self.assertContains(response, 'insurance-TOTAL_FORMS')
        data = self.insurance_form_data()
        data['insurance-INITIAL_FORMS'] = '0'
        data['employee'] = self.emp.pk  # Không được thay nhân viên đã chọn ở URL.
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PayrollInput.objects.get(employee=self.other).insurance_rates['BHXH'], '0.08')

    def test_input_form_closed_record_is_readonly(self):
        row = self.calculate()
        approve_record(self.director, row.pk)
        obj = PayrollInput.objects.get(employee=self.emp)
        self.client.force_login(self.hr)
        response = self.client.get(f'/payroll/inputs/tax/{obj.pk}/')
        self.assertContains(response, 'Dữ liệu được khóa')
        self.assertNotContains(response, 'id="pr-input-form"')
        response = self.client.post(f'/payroll/inputs/tax/{obj.pk}/', self.insurance_form_data())
        self.assertEqual(response.status_code, 200)
        obj.refresh_from_db()
        self.assertEqual(obj.insurance_rates, {'BH': '0.1'})
