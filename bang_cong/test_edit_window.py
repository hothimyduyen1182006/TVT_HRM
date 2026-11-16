from datetime import date, time
from unittest.mock import patch

from django.test import TestCase

from .models import ChamCong, LichSuDieuChinhCong
from . import test_bulk_approval


@patch('bang_cong.services.quy_trinh.timezone.localdate', return_value=date(2026, 11, 15))
class AttendanceEditHistoryTests(TestCase):
    setUp = test_bulk_approval.BulkApprovalTests.setUp

    def record(self, day=8):
        return ChamCong.objects.create(
            nhan_vien=self.employees[0], ngay=date(2026, 11, day),
            gio_vao=time(8), gio_ra=time(17), trang_thai='present',
        )

    def test_edit_saves_old_new_actor_reason_and_displays_history(self, today):
        row = self.record()
        response = self.client.post(f'/bang_cong/{row.pk}/sua/', {
            'gio_vao': '08:00', 'gio_ra': '16:00', 'trang_thai': 'present',
            'reason': 'Correct checkout from clock log',
        })
        self.assertRedirects(response, f'/bang_cong/nhan-vien/{row.nhan_vien_id}/?month=11&year=2026')
        row.refresh_from_db()
        self.assertEqual(row.gio_ra, time(16))
        change = LichSuDieuChinhCong.objects.get(cham_cong=row, truong_dieu_chinh='check_out')
        self.assertEqual(change.gia_tri_cu, '17:00:00')
        self.assertEqual(change.gia_tri_moi, '16:00:00')
        self.assertEqual(change.nguoi_thuc_hien, self.hr)
        self.assertEqual(change.ly_do, 'Correct checkout from clock log')
        history = f'/bang_cong/nhan-vien/{row.nhan_vien_id}/lich-su/?month=11&year=2026'
        self.assertContains(self.client.get(history), change.ly_do)

    def test_expired_and_approved_records_block_get_and_post(self, today):
        expired = self.record(7)
        for method in (self.client.get, self.client.post):
            self.assertEqual(method(f'/bang_cong/{expired.pk}/sua/').status_code, 403)
        recent = self.record(15)
        self.period.trang_thai = 'approved'
        self.period.save()
        for method in (self.client.get, self.client.post):
            self.assertEqual(method(f'/bang_cong/{recent.pk}/sua/').status_code, 403)
        self.assertFalse(LichSuDieuChinhCong.objects.exists())

    def test_month_links_recent_dates_and_keeps_action_column_removed(self, today):
        recent = self.record(15)
        expired = self.record(7)
        response = self.client.get(f'/bang_cong/nhan-vien/{recent.nhan_vien_id}/?month=11&year=2026')
        self.assertContains(response, f'href="/bang_cong/{recent.pk}/sua/"')
        self.assertNotContains(response, f'href="/bang_cong/{expired.pk}/sua/"')
        self.assertNotContains(response, '<th>Tác vụ</th>')

    def test_reason_is_required_and_director_without_hr_cannot_edit(self, today):
        row = self.record()
        url = f'/bang_cong/{row.pk}/sua/'
        response = self.client.post(url, {'gio_vao': '08:00', 'gio_ra': '16:00', 'trang_thai': 'present'})
        self.assertEqual(response.status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.gio_ra, time(17))
        self.assertFalse(LichSuDieuChinhCong.objects.exists())
        self.client.force_login(self.director)
        self.assertEqual(self.client.get(url).status_code, 403)
