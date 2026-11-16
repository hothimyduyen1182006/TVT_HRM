from datetime import time
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, Client

from bang_cong import test_bulk_approval
from bang_cong.models import ChamCong
from bang_cong.services.tinh_toan import lich_thang
from .models import Luong, PayrollAuditLog
from .services.quy_trinh import gui_bang_luong, xu_ly_trang_thai_luong
from .services.tinh_toan import tinh_bang_luong, cap_nhat_luong_nhan_vien


class PayrollSubmissionTests(TestCase):
    def setUp(self):
        test_bulk_approval.BulkApprovalTests.setUp(self)
        self.period.trang_thai = 'approved'
        self.period.ds_nhan_vien = [e.pk for e in self.employees]
        self.period.save()
        days = [day.ngay for day in lich_thang(2026, 11, self.period).values() if day.loai_ngay == 'work']
        for employee in self.employees:
            employee.base_salary = Decimal('8000000')
            employee.payroll_settings = {
                'verified': True, 'insurance_base': '8000000', 'insurance_rates': {'BHXH': '0.08'},
                'insurance_basis': 'Confirmed insurance', 'tax_method': 'legacy',
                'tax_amount': '0', 'tax_basis': 'Confirmed tax', 'lunch_allowance': '450000',
            }
            employee.save()
            ChamCong.objects.bulk_create([ChamCong(
                nhan_vien=employee, ngay=day, gio_vao=time(8), gio_ra=time(17), trang_thai='present',
            ) for day in days])
        tinh_bang_luong(self.hr, self.period.pk, 'Prepare payroll')
        self.transition = f'/bang_luong/period/{self.period.pk}/'

    def test_hr_submits_whole_month_and_director_approves_all(self):
        response = self.client.post(self.transition + '?employee=999999', {
            'action': 'submit',
        })
        self.assertEqual(response.status_code, 302)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'submitted')
        self.assertEqual(self.period.submitted_by, self.hr)
        self.assertIsNotNone(self.period.submitted_at)
        log = PayrollAuditLog.objects.get(period=self.period, action='submit')
        self.assertEqual(log.reason, 'HR đã kiểm tra và gửi tất cả phiếu lương cho Giám đốc.')
        self.assertEqual(len(log.snapshot), 2)
        self.assertEqual(self.period.records.filter(trang_thai='Cho_duyet').count(), 2)
        self.client.force_login(self.director)
        response = self.client.post(self.transition, {'action': 'approve', 'reason': 'Director approved'})
        self.assertEqual(response.status_code, 302)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'approved')
        self.assertEqual(self.period.approved_by, self.director)
        self.assertEqual(self.period.records.filter(trang_thai='Da_duyet').count(), 2)

    def test_director_cannot_approve_before_submission(self):
        with self.assertRaises(ValidationError):
            xu_ly_trang_thai_luong(self.director, self.period.pk, 'approve', 'Bypass')
        self.assertFalse(self.period.records.exclude(trang_thai='Cho_duyet').exists())

    def test_individual_approval_urls_are_removed_before_and_after_submission(self):
        before = list(self.period.records.values())
        for submitted in (False, True):
            if submitted:
                gui_bang_luong(self.hr, self.period.pk, 'HR reviewed')
            for actor in (self.hr, self.director, self.manager, self.employees[0].user):
                self.client.force_login(actor)
                url = f'/bang_luong/{self.period.records.first().pk}/approve/'
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.post(url, {}).status_code, 404)
            self.assertEqual(list(self.period.records.values()), before)

    def test_only_hr_can_submit_and_only_director_can_approve(self):
        for actor in (self.director, self.manager, self.employees[0].user):
            with self.assertRaises(PermissionDenied):
                gui_bang_luong(actor, self.period.pk, 'Review')
        gui_bang_luong(self.hr, self.period.pk, 'Review')
        with self.assertRaises(PermissionDenied):
            xu_ly_trang_thai_luong(self.hr, self.period.pk, 'approve', 'HR cannot approve')
        with self.assertRaises(ValidationError):
            gui_bang_luong(self.hr, self.period.pk, 'Duplicate submission')

    def test_missing_payslips_or_unclosed_attendance_prevent_submission(self):
        self.period.trang_thai = 'pending'
        self.period.save()
        with self.assertRaises(ValidationError):
            gui_bang_luong(self.hr, self.period.pk, 'Unclosed attendance')
        self.period.trang_thai = 'approved'
        self.period.save()
        self.period.records.first().delete()
        with self.assertRaises(ValidationError):
            gui_bang_luong(self.hr, self.period.pk, 'Missing payslip')
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'pending')
        self.assertFalse(PayrollAuditLog.objects.filter(action='submit').exists())

    def test_invalid_source_rolls_back_submission(self):
        with patch('bang_luong.services.quy_trinh.loi_duyet_luong', side_effect=['', 'Stale source']):
            with self.assertRaises(ValidationError):
                gui_bang_luong(self.hr, self.period.pk, 'Review')
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'pending')
        self.assertIsNone(self.period.submitted_by)
        self.assertFalse(PayrollAuditLog.objects.filter(action='submit').exists())

    def test_submitted_payroll_freezes_calculation_and_revalidates_source(self):
        gui_bang_luong(self.hr, self.period.pk, 'Review')
        before = list(self.period.records.values())
        with self.assertRaises(ValidationError):
            tinh_bang_luong(self.hr, self.period.pk, 'Recalculate')
        employee = self.employees[0]
        employee.base_salary += Decimal('1000')
        employee.save()
        cap_nhat_luong_nhan_vien(self.hr, employee.pk, 2026, 11)
        self.assertEqual(list(self.period.records.values()), before)
        with self.assertRaises(ValidationError):
            xu_ly_trang_thai_luong(self.director, self.period.pk, 'approve', 'Source changed')
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'submitted')
        self.assertFalse(self.period.records.exclude(trang_thai='Cho_duyet').exists())

    def test_return_to_hr_requires_resubmission(self):
        gui_bang_luong(self.hr, self.period.pk, 'Review')
        xu_ly_trang_thai_luong(self.director, self.period.pk, 'reopen', 'Check again')
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'pending')
        self.assertIsNone(self.period.submitted_by)
        self.assertIsNone(self.period.submitted_at)
        with self.assertRaises(ValidationError):
            xu_ly_trang_thai_luong(self.director, self.period.pk, 'approve', 'Must resubmit')
        gui_bang_luong(self.hr, self.period.pk, 'HR rechecked')
        xu_ly_trang_thai_luong(self.director, self.period.pk, 'approve', 'Approved')

    def test_ui_roles_csrf_and_post_only(self):
        url = '/bang_luong/?month=11&year=2026'
        response = self.client.get(url)
        self.assertContains(response, 'value="submit"')
        self.assertNotContains(response, 'id="pr-review-note"')
        self.assertNotContains(response, 'value="approve"')
        self.assertEqual(self.client.get(self.transition).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.hr)
        self.assertEqual(csrf_client.post(self.transition, {'action': 'submit', 'reason': 'Review'}).status_code, 403)
        gui_bang_luong(self.hr, self.period.pk, 'Review')
        self.assertNotContains(self.client.get(url), 'value="submit"')
        self.client.force_login(self.director)
        self.assertContains(self.client.get(url), 'value="approve"')

    def test_payment_remains_available_after_approval(self):
        gui_bang_luong(self.hr, self.period.pk, 'Review')
        xu_ly_trang_thai_luong(self.director, self.period.pk, 'approve', 'Approve')
        xu_ly_trang_thai_luong(self.director, self.period.pk, 'paid', 'Payment', 'BANK-123')
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'paid')
        self.assertEqual(self.period.records.filter(trang_thai='Da_chi_tra').count(), 2)
