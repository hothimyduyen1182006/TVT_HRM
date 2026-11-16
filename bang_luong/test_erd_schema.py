from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection, IntegrityError, transaction
from django.test import TestCase

from . import test_submission
from .models import Luong, PayrollAuditLog
from .services.quy_trinh import gui_bang_luong, xu_ly_trang_thai_luong
from .services.tinh_toan import tinh_bang_luong


class SalaryERDSchemaTests(TestCase):
    setUp = test_submission.PayrollSubmissionTests.setUp

    def test_only_twelve_columns_and_business_key(self):
        expected = {'Ma_luong', 'Ma_tong_hop', 'Ma_thuong', 'Luong_co_ban', 'Luong_theo_cong',
            'Luong_tang_ca', 'Tong_tien_thuong', 'Khau_tru_di_tre', 'Khau_tru_BHXH',
            'Thue_TNCN', 'Luong_thuc_linh', 'Trang_thai'}
        self.assertEqual({field.column for field in Luong._meta.concrete_fields}, expected)
        with connection.cursor() as cursor:
            columns = connection.introspection.get_table_description(cursor, 'Luong')
        self.assertEqual({column.name for column in columns}, expected)
        self.assertEqual(Luong._meta.pk.name, 'ma_luong')
        self.assertEqual(Luong._meta.pk.max_length, 20)
        for name in ('luong_co_ban', 'luong_theo_cong', 'luong_tang_ca', 'tong_tien_thuong',
                     'khau_tru_di_tre', 'khau_tru_bhxh', 'thue_tncn', 'luong_thuc_linh'):
            field = Luong._meta.get_field(name)
            self.assertEqual((field.max_digits, field.decimal_places), (12, 0))

    def test_details_personal_home_and_export_work_with_string_key(self):
        row = self.period.records.first()
        self.assertEqual(row.pk, row.ma_luong)
        self.assertEqual(row.tong_thuong_id, row.tong_thuong.ma_thuong)
        self.assertEqual(self.client.get(f'/bang_luong/{row.pk}/').status_code, 200)
        self.assertContains(self.client.get('/bang_luong/?month=11&year=2026'), row.ten_nhan_vien)
        gui_bang_luong(self.hr, self.period.pk, 'Review')
        xu_ly_trang_thai_luong(self.director, self.period.pk, 'approve', 'Approve all')
        for fmt in ('csv', 'json', 'txt'):
            self.assertEqual(self.client.post(f'/bang_luong/export/{fmt}/',
                {'month': 11, 'year': 2026}).status_code, 200)
        self.client.force_login(row.nhan_vien.user)
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertContains(self.client.get('/bang_luong/personal/?month=11&year=2026'), row.ten_nhan_vien)

    def test_salary_snapshot_is_archived_and_recalculation_keeps_business_key(self):
        row = self.period.records.first()
        old_key = row.pk
        old_details = row.chi_tiet.copy()
        self.assertTrue(PayrollAuditLog.objects.filter(action='salary_detail', snapshot__ma_luong=old_key).exists())
        tinh_bang_luong(self.hr, self.period.pk, 'Recalculate')
        row.refresh_from_db()
        self.assertEqual(row.pk, old_key)
        self.assertEqual(row.chi_tiet, old_details)
        self.assertEqual(self.period.records.count(), 2)

    def test_money_rounding_bounds_status_and_unique_links(self):
        row = self.period.records.first()
        row.luong_tang_ca = Decimal('100.5')
        row.save(update_fields=['luong_tang_ca'])
        row.refresh_from_db()
        self.assertEqual(row.luong_tang_ca, 101)
        row.luong_tang_ca = Decimal('1000000000000')
        with self.assertRaises(ValidationError):
            row.save(update_fields=['luong_tang_ca'])
        with self.assertRaises(IntegrityError), transaction.atomic():
            Luong.objects.filter(pk=row.pk).update(trang_thai='pending')
        other = self.period.records.exclude(pk=row.pk).first()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Luong.objects.filter(pk=other.pk).update(tong_hop_id=row.tong_hop_id)
