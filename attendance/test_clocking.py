from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from django.test import TestCase
from .tests import AttendanceTests
from .models import AttendanceRecord, AttendanceAuditLog, EmployeeAttendanceApproval, AttendancePeriod, WorkCalendarDay
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
            AttendanceRecord.objects.create(employee=self.emp, date=date(2026,1,5),
                check_in=time(8), check_out=time(17), status='present', updated_by=self.hr)
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


class AutomaticMonthClockTests(TestCase):
    def setUp(self):
        AttendanceTests.setUp(self)
        self.period.month = 10
        self.period.save()
        WorkCalendarDay.objects.all().delete()
        for number in range(1, 32):
            day = date(2026, 10, number)
            work = day.weekday() < 5
            WorkCalendarDay.objects.create(date=day, kind='work' if work else 'rest', expected_units=1 if work else 0)
        self.client.force_login(self.user)

    def at(self, number=11, hour=8):
        return patch('django.utils.timezone.localtime', return_value=datetime(2026, 11, number, hour,
            tzinfo=ZoneInfo('Asia/Ho_Chi_Minh')))

    def test_get_previews_inherited_shift_without_writing(self):
        with self.at():
            response = self.client.get(reverse('attendance:clock'))
        self.assertTrue(response.context['can_check_in'])
        self.assertEqual(response.context['period'].start_time, time(8))
        self.assertIsNone(response.context['period'].pk)
        self.assertContains(response, 'value="in"')
        self.assertEqual(AttendancePeriod.objects.count(), 1)
        self.assertEqual(WorkCalendarDay.objects.count(), 31)
        self.assertFalse(AttendanceRecord.objects.exists())
        self.assertFalse(AttendanceAuditLog.objects.exists())

    def test_successful_checkin_opens_one_period_and_preserves_source(self):
        before = list(WorkCalendarDay.objects.order_by('date').values())
        source = AttendancePeriod.objects.values().get(pk=self.period.pk)
        with self.at():
            response = self.client.post(reverse('attendance:clock'), {'action':'in','employee':self.other.pk,'check_in':'06:00'})
            self.assertEqual(response.status_code, 302)
            row = AttendanceRecord.objects.get(employee=self.emp)
            self.assertEqual(row.check_in, time(8))
            self.assertEqual(row.date, date(2026, 11, 11))
            punch(self.other_user, 'in')
            with self.assertRaises(ValidationError): punch(self.user, 'in')
        period = AttendancePeriod.objects.get(year=2026, month=11)
        self.assertEqual(period.status, 'pending')
        self.assertTrue(period.policy_confirmed)
        self.assertEqual(period.employee_ids, [])
        self.assertFalse(period.employee_approvals.exists())
        self.assertEqual(AttendancePeriod.objects.count(), 2)
        self.assertEqual(WorkCalendarDay.objects.filter(date__year=2026,date__month=11).count(), 30)
        self.assertEqual(AttendanceAuditLog.objects.filter(action='auto_open_period').count(), 1)
        self.assertEqual(before, list(WorkCalendarDay.objects.filter(date__month=10).order_by('date').values()))
        self.assertEqual(source, AttendancePeriod.objects.values().get(pk=self.period.pk))
        with self.at(hour=17):
            row = punch(self.user, 'out')
            self.assertEqual(row.work_hours, 8)
            self.assertEqual(row.paid_units, 1)
            with self.assertRaises(ValidationError): punch(self.user, 'out')

    def test_failed_checkout_and_invalid_action_roll_back_initialization(self):
        with self.at():
            for action in ['out','invalid']:
                with self.assertRaises(ValidationError): punch(self.user, action)
        self.assertEqual(AttendancePeriod.objects.count(), 1)
        self.assertEqual(WorkCalendarDay.objects.count(), 31)
        self.assertFalse(AttendanceAuditLog.objects.exists())

    def test_weekly_rest_does_not_open_period_or_allow_punch(self):
        with self.at(number=14):
            response = self.client.get(reverse('attendance:clock'))
            self.assertFalse(response.context['can_check_in'])
            with self.assertRaises(ValidationError): punch(self.user, 'in')
        self.assertEqual(AttendancePeriod.objects.count(), 1)

    def test_explicit_holiday_is_kept_when_month_is_opened(self):
        holiday = WorkCalendarDay.objects.create(date=date(2026,11,13),kind='holiday',expected_units=0,name='Ngày nghỉ đã cấu hình')
        before = WorkCalendarDay.objects.values().get(pk=holiday.pk)
        with self.at(): punch(self.user,'in')
        self.assertEqual(before, WorkCalendarDay.objects.values().get(pk=holiday.pk))
        with self.at(number=13):
            response = self.client.get(reverse('attendance:clock'))
            self.assertFalse(response.context['can_check_in'])
            with self.assertRaises(ValidationError): punch(self.other_user,'in')

    def test_missing_or_unconfirmed_source_does_not_guess_a_shift(self):
        self.period.policy_confirmed = False
        self.period.save()
        with self.at():
            response = self.client.get(reverse('attendance:clock'))
            self.assertFalse(response.context['can_check_in'])
            with self.assertRaises(ValidationError): punch(self.user,'in')
        self.assertEqual(AttendancePeriod.objects.count(),1)

    def test_future_policy_is_not_applied_before_its_month(self):
        AttendancePeriod.objects.create(year=2026,month=12,start_time=time(9),lunch_start=time(12),
            lunch_end=time(13),end_time=time(18),standard_hours=8,policy_confirmed=True)
        with self.at(): punch(self.user,'in')
        self.assertEqual(AttendancePeriod.objects.get(year=2026,month=11).start_time,time(8))

    def test_leap_year_month_is_initialized_with_correct_day_count(self):
        with patch('django.utils.timezone.localtime',return_value=datetime(2028,2,14,8,
                   tzinfo=ZoneInfo('Asia/Ho_Chi_Minh'))):
            punch(self.user,'in')
        self.assertEqual(WorkCalendarDay.objects.filter(date__year=2028,date__month=2).count(),29)
        self.assertTrue(WorkCalendarDay.objects.filter(date=date(2028,2,29)).exists())

    def test_partial_source_calendar_is_not_used(self):
        WorkCalendarDay.objects.filter(date=date(2026,10,31)).delete()
        with self.at():
            with self.assertRaisesMessage(ValidationError,'chưa đủ tháng'): punch(self.user,'in')
        self.assertEqual(AttendancePeriod.objects.count(),1)

    def test_irregular_weekly_calendar_is_not_silently_inferred(self):
        WorkCalendarDay.objects.filter(date=date(2026,10,7)).update(kind='rest',expected_units=0)
        with self.at():
            with self.assertRaisesMessage(ValidationError,'ngoại lệ'): punch(self.user,'in')
        self.assertEqual(AttendancePeriod.objects.count(),1)

    def test_existing_unconfirmed_month_is_not_overwritten(self):
        period = AttendancePeriod.objects.create(year=2026,month=11,start_time=time(9),lunch_start=time(12),
            lunch_end=time(13),end_time=time(18),standard_hours=8,policy_confirmed=False)
        with self.at():
            with self.assertRaises(ValidationError): punch(self.user,'in')
        period.refresh_from_db()
        self.assertFalse(period.policy_confirmed)
        self.assertEqual(period.start_time,time(9))
        self.assertFalse(WorkCalendarDay.objects.filter(date__month=11).exists())

    def test_source_approval_is_not_copied_and_new_month_can_still_be_locked(self):
        self.period.status='approved'
        self.period.save()
        EmployeeAttendanceApproval.objects.create(period=self.period,employee=self.emp,approved_by=self.hr)
        with self.at(): punch(self.user,'in')
        period=AttendancePeriod.objects.get(month=11,year=2026)
        self.assertEqual(period.status,'pending')
        self.assertFalse(period.employee_approvals.exists())
        period.status='approved'
        period.save()
        with self.at(hour=17):
            with self.assertRaises(ValidationError): punch(self.user,'out')
        self.assertIsNone(AttendanceRecord.objects.get(employee=self.emp,date=date(2026,11,11)).check_out)

    def test_authentication_csrf_and_hire_date_do_not_create_calendar(self):
        from django.test import Client
        url=reverse('attendance:clock')
        anonymous=Client()
        self.assertEqual(anonymous.post(url,{'action':'in'}).status_code,302)
        client=Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(url,{'action':'in'}).status_code,403)
        with self.at():
            with self.assertRaises(PermissionDenied): punch(AnonymousUser(),'in')
            self.emp.hire_date=date(2026,12,1)
            self.emp.save()
            with self.assertRaises(ValidationError): punch(self.user,'in')
        self.assertEqual(AttendancePeriod.objects.count(),1)
        self.assertFalse(AttendanceRecord.objects.exists())
