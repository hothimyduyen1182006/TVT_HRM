from datetime import date, time
from decimal import Decimal
from django.test import TestCase
from nghi_phep.models import LeaveDay
from .tests import AttendanceTests
from .services.quy_trinh import luu_cham_cong


class StatFilterTests(TestCase):
    setUp = AttendanceTests.setUp
    record = AttendanceTests.record

    def test_cards_filter_daily_rows_and_preserve_period(self):
        regular = luu_cham_cong(self.hr, self.record(gio_ra=time(19)), 'Ngày làm')
        late = luu_cham_cong(self.hr, self.record(ngay=date(2026, 1, 6), gio_vao=time(9)), 'Đi trễ')
        LeaveDay.objects.create(employee=self.emp, date=date(2026, 1, 7), units=1,
                                paid=True, approved=True, reason='Phép')
        leave = luu_cham_cong(self.hr, self.record(ngay=date(2026, 1, 7), gio_vao=None,
                            gio_ra=None, trang_thai='leave'), 'Nghỉ phép')
        absent = luu_cham_cong(self.hr, self.record(ngay=date(2026, 1, 8), gio_vao=None,
                             gio_ra=None, trang_thai='absent'), 'Vắng')
        self.client.force_login(self.hr)
        url = f'/bang_cong/nhan-vien/{self.emp.pk}/'
        expected = {'actual': [regular.ngay, late.ngay], 'paid_leave': [leave.ngay],
                    'paid': [regular.ngay, late.ngay, leave.ngay], 'absent': [absent.ngay],
                    'late': [late.ngay], 'ot': [regular.ngay]}
        for state, dates in expected.items():
            with self.subTest(state=state):
                response = self.client.get(url, {'month': 1, 'year': 2026, 'state': state,
                    'start': '2026-01-05', 'end': '2026-01-08', 'page': 3})
                self.assertEqual(response.status_code, 200)
                self.assertCountEqual([row['date'] for row in response.context['rows']], dates)
                query = response.context['stat_query']
                self.assertIn('month=1', query)
                self.assertIn('start=2026-01-05', query)
                self.assertNotIn('page=', query)
                self.assertNotIn('state=', query)
                self.assertContains(response, '&amp;state=paid_leave')
                self.assertContains(response, '&amp;state=ot')
                self.assertEqual(response.context['summary']['paid'], Decimal('2.875'))
