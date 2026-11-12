from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from django.test import TestCase
from .tests import AttendanceTests
from .models import ChamCong, NhatKyCong, ChotBangCong, KyCong, LichLamViec
from .services.clocking import punch


class ClockTests(TestCase):
    setUp = AttendanceTests.setUp
    def at(self, hour, minute=0):
        return patch('django.utils.timezone.localtime', return_value=datetime(2026, 1, 5, hour, minute, tzinfo=ZoneInfo('Asia/Ho_Chi_Minh')))

    def test_punch_lifecycle(self):
        with self.at(8):
            row = punch(self.user, 'in')
            self.assertEqual(row.trang_thai, 'incomplete')
            self.assertEqual(row.tong_cong, 0)
            with self.assertRaises(ValidationError):
                punch(self.user, 'in')
        with self.at(17):
            row = punch(self.user, 'out', 'Hoàn thành công việc')
            self.assertEqual(row.so_gio_lam, 8)
            self.assertEqual(row.tong_cong, 1)
            self.assertEqual(row.ghi_chu, 'Hoàn thành công việc')
            with self.assertRaises(ValidationError):
                punch(self.user, 'out')
        self.assertFalse(NhatKyCong.objects.exists())

    def test_late_checkout_does_not_submit_or_approve_ot(self):
        from .models import LichSuTangCa
        with self.at(8):
            punch(self.user, 'in')
        with self.at(19):
            row = punch(self.user, 'out')
        self.assertEqual(row.gio_ra, time(19))
        self.assertEqual(row.so_gio_lam, 8)
        self.assertFalse(LichSuTangCa.objects.exists())

    def test_out_without_in_and_approved_lock(self):
        with self.at(9):
            with self.assertRaises(ValidationError):
                punch(self.user, 'out')
            ChamCong.objects.create(nhan_vien=self.emp, ngay=date(2026,1,5),
                gio_vao=time(8), gio_ra=time(17), trang_thai='present', nguoi_cap_nhat=self.hr)
            ChotBangCong.objects.create(ky_cong=self.period, nhan_vien=self.emp, nguoi_duyet=self.hr)
            with self.assertRaises(ValidationError):
                punch(self.user, 'in')

    def test_view_uses_own_employee_and_server_time(self):
        self.client.force_login(self.user)
        url = reverse('bang_cong:clock')
        with self.at(8, 15):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(ChamCong.objects.exists())
            self.client.post(url, {'action': 'in', 'employee': self.other.pk, 'check_in': '07:00'})
            row = ChamCong.objects.get()
            self.assertEqual(row.nhan_vien, self.emp)
            self.assertEqual(row.gio_vao, time(8, 15))
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
        self.assertEqual(self.client.get(reverse('bang_cong:clock')).status_code, 403)

    def test_invalid_shift_blocks_punch_even_with_old_confirmation(self):
        for values in [{'gio_chuan': 0}, {'gio_chuan': -1}, {'ket_thuc_nghi_trua': time(11)}]:
            with self.subTest(values=values):
                KyCong.objects.filter(pk=self.period.pk).update(gio_chuan=8, ket_thuc_nghi_trua=time(13))
                KyCong.objects.filter(pk=self.period.pk).update(**values)
                with self.at(8), self.assertRaises(ValidationError):
                    punch(self.user, 'in')
                self.assertFalse(ChamCong.objects.exists())

    def test_incomplete_or_invalid_calendar_blocks_punch(self):
        LichLamViec.objects.filter(ngay=date(2026,1,31)).delete()
        with self.at(8), self.assertRaises(ValidationError):
            punch(self.user, 'in')
        LichLamViec.objects.create(ngay=date(2026,1,31),loai_ngay='rest',cong_chuan=1)
        with self.at(8), self.assertRaises(ValidationError):
            punch(self.user, 'in')
        self.assertFalse(ChamCong.objects.exists())

    def test_valid_period_can_be_approved_without_confirmation(self):
        from .services.workflow import approve_employee
        for day in LichLamViec.objects.filter(loai_ngay='work'):
            AttendanceTests.record(self, ngay=day.ngay, nguoi_cap_nhat=self.hr).save()
        approval = approve_employee(self.hr, self.emp, self.period.pk)
        self.assertEqual(approval.nhan_vien_id, self.emp.pk)
        self.period.refresh_from_db()
        self.assertNotIn('policy_confirmed', [field.name for field in KyCong._meta.fields])


class AutomaticMonthClockTests(TestCase):
    def setUp(self):
        AttendanceTests.setUp(self)
        self.period.thang = 10
        self.period.save()
        LichLamViec.objects.all().delete()
        for number in range(1, 32):
            day = date(2026, 10, number)
            work = day.weekday() < 5
            LichLamViec.objects.create(ngay=day, loai_ngay='work' if work else 'rest', cong_chuan=1 if work else 0)
        self.client.force_login(self.user)

    def at(self, number=11, hour=8):
        return patch('django.utils.timezone.localtime', return_value=datetime(2026, 11, number, hour,
            tzinfo=ZoneInfo('Asia/Ho_Chi_Minh')))

    def test_get_previews_inherited_shift_without_writing(self):
        with self.at():
            response = self.client.get(reverse('bang_cong:clock'))
        self.assertTrue(response.context['can_check_in'])
        self.assertEqual(response.context['period'].gio_bat_dau, time(8))
        self.assertIsNone(response.context['period'].pk)
        self.assertContains(response, 'value="in"')
        self.assertEqual(KyCong.objects.count(), 1)
        self.assertEqual(LichLamViec.objects.count(), 31)
        self.assertFalse(ChamCong.objects.exists())
        self.assertFalse(NhatKyCong.objects.exists())

    def test_successful_checkin_opens_one_period_and_preserves_source(self):
        before = list(LichLamViec.objects.order_by('ngay').values())
        source = KyCong.objects.values().get(pk=self.period.pk)
        with self.at():
            response = self.client.post(reverse('bang_cong:clock'), {'action':'in','employee':self.other.pk,'check_in':'06:00'})
            self.assertEqual(response.status_code, 302)
            row = ChamCong.objects.get(nhan_vien=self.emp)
            self.assertEqual(row.gio_vao, time(8))
            self.assertEqual(row.ngay, date(2026, 11, 11))
            punch(self.other_user, 'in')
            with self.assertRaises(ValidationError): punch(self.user, 'in')
        period = KyCong.objects.get(nam=2026, thang=11)
        self.assertEqual(period.trang_thai, 'pending')
        self.assertNotIn('policy_confirmed', [field.name for field in KyCong._meta.fields])
        self.assertEqual(period.ds_nhan_vien, [])
        self.assertFalse(period.employee_approvals.exists())
        self.assertEqual(KyCong.objects.count(), 2)
        self.assertEqual(LichLamViec.objects.filter(ngay__year=2026,ngay__month=11).count(), 30)
        self.assertEqual(NhatKyCong.objects.filter(hanh_dong='auto_open_period').count(), 1)
        self.assertEqual(before, list(LichLamViec.objects.filter(ngay__month=10).order_by('ngay').values()))
        self.assertEqual(source, KyCong.objects.values().get(pk=self.period.pk))
        with self.at(hour=17):
            row = punch(self.user, 'out')
            self.assertEqual(row.so_gio_lam, 8)
            self.assertEqual(row.tong_cong, 1)
            with self.assertRaises(ValidationError): punch(self.user, 'out')

    def test_failed_checkout_and_invalid_action_roll_back_initialization(self):
        with self.at():
            for action in ['out','invalid']:
                with self.assertRaises(ValidationError): punch(self.user, action)
        self.assertEqual(KyCong.objects.count(), 1)
        self.assertEqual(LichLamViec.objects.count(), 31)
        self.assertFalse(NhatKyCong.objects.exists())

    def test_weekly_rest_does_not_open_period_or_allow_punch(self):
        with self.at(number=14):
            response = self.client.get(reverse('bang_cong:clock'))
            self.assertFalse(response.context['can_check_in'])
            with self.assertRaises(ValidationError): punch(self.user, 'in')
        self.assertEqual(KyCong.objects.count(), 1)

    def test_explicit_holiday_is_kept_when_month_is_opened(self):
        holiday = LichLamViec.objects.create(ngay=date(2026,11,13),loai_ngay='holiday',cong_chuan=0,ghi_chu='Ngày nghỉ đã cấu hình')
        before = LichLamViec.objects.values().get(pk=holiday.pk)
        with self.at(): punch(self.user,'in')
        self.assertEqual(before, LichLamViec.objects.values().get(pk=holiday.pk))
        with self.at(number=13):
            response = self.client.get(reverse('bang_cong:clock'))
            self.assertFalse(response.context['can_check_in'])
            with self.assertRaises(ValidationError): punch(self.other_user,'in')

    def test_valid_source_is_used_without_manual_confirmation(self):
        self.period.save()
        with self.at():
            response = self.client.get(reverse('bang_cong:clock'))
            self.assertTrue(response.context['can_check_in'])
            punch(self.user,'in')
        self.assertEqual(KyCong.objects.count(),2)

    def test_future_policy_is_not_applied_before_its_month(self):
        KyCong.objects.create(nam=2026,thang=12,gio_bat_dau=time(9),bat_dau_nghi_trua=time(12),
            ket_thuc_nghi_trua=time(13),gio_ket_thuc=time(18),gio_chuan=8)
        with self.at(): punch(self.user,'in')
        self.assertEqual(KyCong.objects.get(nam=2026,thang=11).gio_bat_dau,time(8))

    def test_leap_year_month_is_initialized_with_correct_day_count(self):
        with patch('django.utils.timezone.localtime',return_value=datetime(2028,2,14,8,
                   tzinfo=ZoneInfo('Asia/Ho_Chi_Minh'))):
            punch(self.user,'in')
        self.assertEqual(LichLamViec.objects.filter(ngay__year=2028,ngay__month=2).count(),29)
        self.assertTrue(LichLamViec.objects.filter(ngay=date(2028,2,29)).exists())

    def test_partial_source_calendar_is_not_used(self):
        LichLamViec.objects.filter(ngay=date(2026,10,31)).delete()
        with self.at():
            with self.assertRaisesMessage(ValidationError,'chưa đủ tháng'): punch(self.user,'in')
        self.assertEqual(KyCong.objects.count(),1)

    def test_irregular_weekly_calendar_is_not_silently_inferred(self):
        LichLamViec.objects.filter(ngay=date(2026,10,7)).update(loai_ngay='rest',cong_chuan=0)
        with self.at():
            with self.assertRaisesMessage(ValidationError,'ngoại lệ'): punch(self.user,'in')
        self.assertEqual(KyCong.objects.count(),1)

    def test_existing_valid_shift_is_kept_without_confirmation(self):
        period = KyCong.objects.create(nam=2026,thang=11,gio_bat_dau=time(9),bat_dau_nghi_trua=time(12),
            ket_thuc_nghi_trua=time(13),gio_ket_thuc=time(18),gio_chuan=8)
        with self.at():
            punch(self.user,'in')
        period.refresh_from_db()
        self.assertNotIn('policy_confirmed', [field.name for field in KyCong._meta.fields])
        self.assertEqual(period.gio_bat_dau,time(9))
        self.assertEqual(LichLamViec.objects.filter(ngay__month=11).count(),30)

    def test_source_approval_is_not_copied_and_new_month_can_still_be_locked(self):
        self.period.trang_thai='approved'
        self.period.save()
        ChotBangCong.objects.create(ky_cong=self.period,nhan_vien=self.emp,nguoi_duyet=self.hr)
        with self.at(): punch(self.user,'in')
        period=KyCong.objects.get(thang=11,nam=2026)
        self.assertEqual(period.trang_thai,'pending')
        self.assertFalse(period.employee_approvals.exists())
        period.trang_thai='approved'
        period.save()
        with self.at(hour=17):
            with self.assertRaises(ValidationError): punch(self.user,'out')
        self.assertIsNone(ChamCong.objects.get(nhan_vien=self.emp,ngay=date(2026,11,11)).gio_ra)

    def test_authentication_csrf_and_hire_date_do_not_create_calendar(self):
        from django.test import Client
        url=reverse('bang_cong:clock')
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
        self.assertEqual(KyCong.objects.count(),1)
        self.assertFalse(ChamCong.objects.exists())
