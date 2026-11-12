from datetime import date, time
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from nghi_phep.models import LeaveDay
from .tests import AttendanceTests
from .services.workflow import save_record


class StatFilterTests(TestCase):
    setUp = AttendanceTests.setUp
    record = AttendanceTests.record

    def test_cards_filter_daily_rows_and_preserve_period(self):
        regular = save_record(self.hr, self.record(check_out=time(19)), 'Ngày làm')
        late = save_record(self.hr, self.record(date=date(2026, 1, 6), check_in=time(9)), 'Đi trễ')
        LeaveDay.objects.create(employee=self.emp, date=date(2026, 1, 7), units=1,
                                paid=True, approved=True, reason='Phép')
        leave = save_record(self.hr, self.record(date=date(2026, 1, 7), check_in=None,
                            check_out=None, status='leave'), 'Nghỉ phép')
        absent = save_record(self.hr, self.record(date=date(2026, 1, 8), check_in=None,
                             check_out=None, status='absent'), 'Vắng')
        self.client.force_login(self.hr)
        url = f'/bang_cong/employee/{self.emp.pk}/'
        expected = {'actual': [regular.date, late.date], 'paid_leave': [leave.date],
                    'paid': [regular.date, late.date, leave.date], 'absent': [absent.date],
                    'late': [late.date], 'ot': [regular.date]}
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
