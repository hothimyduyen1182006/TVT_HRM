from datetime import datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.test import TestCase
from .tests import AttendanceTests
from .models import AttendanceRecord, AttendanceAuditLog, EmployeeAttendanceApproval
from .services.clocking import punch


class ClockTests(TestCase):
    setUp = AttendanceTests.setUp
    def at(self, hour, minute=0):
        return patch('django.utils.timezone.localtime', return_value=datetime(2026, 1, 5, hour, minute, tzinfo=ZoneInfo('Asia/Ho_Chi_Minh')))

    def test_punch_lifecycle(self):
        with self.at(8):
            row = punch(self.user, 'in')
            self.assertEqual(row.status, 'incomplete')
            self.assertEqual(row.paid_units, 0)
            with self.assertRaises(ValidationError):
                punch(self.user, 'in')
        with self.at(17):
            row = punch(self.user, 'out', 'Hoàn thành công việc')
            self.assertEqual(row.work_hours, 8)
            self.assertEqual(row.paid_units, 1)
            self.assertEqual(row.note, 'Hoàn thành công việc')
            with self.assertRaises(ValidationError):
                punch(self.user, 'out')
        self.assertFalse(AttendanceAuditLog.objects.exists())

    def test_late_checkout_does_not_submit_or_approve_ot(self):
        from .models import OvertimeApproval
        with self.at(8):
            punch(self.user, 'in')
        with self.at(19):
            row = punch(self.user, 'out')
        self.assertEqual(row.check_out, time(19))
        self.assertEqual(row.work_hours, 8)
        self.assertFalse(OvertimeApproval.objects.exists())

    def test_out_without_in_and_approved_lock(self):
        with self.at(9):
            with self.assertRaises(ValidationError):
                punch(self.user, 'out')
            EmployeeAttendanceApproval.objects.create(period=self.period, employee=self.emp, approved_by=self.hr)
            with self.assertRaises(ValidationError):
                punch(self.user, 'in')

    def test_view_uses_own_employee_and_server_time(self):
        self.client.force_login(self.user)
        url = reverse('attendance:clock')
        with self.at(8, 15):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(AttendanceRecord.objects.exists())
            self.client.post(url, {'action': 'in', 'employee': self.other.pk, 'check_in': '07:00'})
            row = AttendanceRecord.objects.get()
            self.assertEqual(row.employee, self.emp)
            self.assertEqual(row.check_in, time(8, 15))
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['success'], 'in')
            self.assertEqual(response.context['page_state'], 'checkout')
            self.assertTrue(response.context['can_check_out'])
        with self.at(17):
            self.client.post(url, {'action': 'out'})
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['success'], 'out')
            self.assertEqual(response.context['page_state'], 'done')
            self.assertFalse(response.context['can_check_out'])

    def test_unlinked_user_denied(self):
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get(reverse('attendance:clock')).status_code, 403)
