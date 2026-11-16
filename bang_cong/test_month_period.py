from datetime import date, time
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from . import test_bulk_approval
from .models import ChamCong


class MonthPeriodTests(TestCase):
    setUp = test_bulk_approval.BulkApprovalTests.setUp

    def test_summary_skips_ot_while_detail_and_saved_summary_keep_it(self):
        from .services.quy_trinh import cap_nhat_tong_hop
        from .services.tinh_toan import tinh_tang_ca_tu_dong
        employee = self.employees[0]
        ChamCong.objects.create(nhan_vien=employee, ngay=date(2026, 11, 10),
                                gio_vao=time(8), gio_ra=time(19), trang_thai='present')
        with patch('bang_cong.services.hien_thi.tinh_tang_ca_tu_dong', wraps=tinh_tang_ca_tu_dong) as overtime:
            response = self.client.get('/bang_cong/?month=11&year=2026')
            self.assertEqual(response.status_code, 200)
            overtime.assert_not_called()
            self.assertNotContains(response, 'OT:')
            self.assertTrue(all('ot' not in row for row in response.context['rows']))
            response = self.client.get(f'/bang_cong/nhan-vien/{employee.pk}/?month=11&year=2026')
            self.assertEqual(response.context['summary']['ot'], Decimal(2))
            self.assertEqual(overtime.call_count, 1)
        summary = cap_nhat_tong_hop(employee, self.period)
        self.assertEqual(summary.gio_tang_ca, Decimal(2))

    def test_month_uses_summary_period_and_ignores_old_daily_filters(self):
        employee = self.employees[0]
        ChamCong.objects.create(nhan_vien=employee, ngay=date(2026, 11, 10),
                                gio_vao=time(9), gio_ra=time(17), trang_thai='present')
        url = f'/bang_cong/nhan-vien/{employee.pk}/'
        response = self.client.get(url, {
            'month': 11, 'year': 2026, 'state': 'invalid', 'start': 'bad', 'end': 'bad',
            'day': 'bad', 'department': 'bad', 'q': 'unrelated', 'page': 2,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['rows']), 30)
        self.assertEqual(response.context['page_obj'].number, 2)
        self.assertEqual(response.context['month_query'], 'month=11&year=2026')
        self.assertEqual(response.context['page_query'], 'month=11&year=2026')
        self.assertNotContains(response, '&amp;state=')
        self.assertNotContains(response, 'at-stat-filter')
        self.assertNotContains(response, 'class="at-filter"')
        summary = self.client.get('/bang_cong/?month=11&year=2026')
        self.assertContains(summary, url + '?month=11&year=2026')

    def test_personal_month_shows_full_month(self):
        employee = self.employees[0]
        query = {'month': 11, 'year': 2026}
        self.client.force_login(employee.user)
        response = self.client.get('/bang_cong/ca-nhan/', query)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['rows']), 30)
        self.assertNotContains(response, 'class="at-filter"')

    def test_invalid_period_uses_default_month(self):
        employee = self.employees[0]
        query = {'month': 13, 'year': 2026}
        response = self.client.get(f'/bang_cong/nhan-vien/{employee.pk}/', query)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['rows']), 30)
