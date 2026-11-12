from datetime import date, time
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from .models import (
    LichSuDieuChinhCong, NhatKyCong, ChamCong,
    ChotBangCong, TongHopCong, LichLamViec,
)
from .services.presentation import history_logs, history_rows
from .services.summaries import payroll_summary, record_adjustments
from .services.workflow import approve_employee, change_period, save_record
from . import tests as attendance_tests


class MonthlySummaryTests(TestCase):
    setUp = attendance_tests.AttendanceTests.setUp

    def record(self, **values):
        return attendance_tests.AttendanceTests.record(self, **values)

    def fill_month(self, employee):
        ChamCong.objects.bulk_create([
            self.record(nhan_vien=employee, ngay=day.ngay, nguoi_cap_nhat=self.hr)
            for day in LichLamViec.objects.filter(loai_ngay='work')
        ])

    def test_repeated_save_updates_one_summary_without_adding_ot_twice(self):
        row = save_record(self.hr, self.record(gio_ra=time(19)), 'Create')
        summary = TongHopCong.objects.get(nhan_vien=self.emp, ky_cong=self.period)
        self.assertEqual((summary.tong_cong, summary.so_gio_lam, summary.gio_tang_ca), (1, 8, 2))
        self.assertEqual(row.so_gio_tang_ca, 2)
        audit_count = NhatKyCong.objects.count()
        save_record(self.hr, row, 'No changes')
        summary.refresh_from_db()
        self.assertEqual(summary.gio_tang_ca, 2)
        self.assertEqual(TongHopCong.objects.count(), 1)
        self.assertEqual(NhatKyCong.objects.count(), audit_count)

    def test_adjustments_keep_original_json_and_history_output(self):
        row = save_record(self.hr, self.record(), 'Create')
        row.gio_ra = time(19)
        save_record(self.hr, row, 'Correct checkout')
        audit = NhatKyCong.objects.get(hanh_dong='edit_record')
        original = (audit.du_lieu_cu.copy(), audit.du_lieu_moi.copy())
        details = {item.truong_dieu_chinh: item for item in audit.adjustments.all()}
        self.assertEqual(details['check_out'].gia_tri_cu, '17:00:00')
        self.assertEqual(details['check_out'].gia_tri_moi, '19:00:00')
        self.assertEqual(details['overtime_hours'].gia_tri_moi, '2.0000')
        self.assertEqual(details['check_out'].cham_cong_id, row.pk)
        count = LichSuDieuChinhCong.objects.count()
        record_adjustments(audit)
        self.assertEqual(LichSuDieuChinhCong.objects.count(), count)
        output = history_rows(history_logs(self.emp, 2026, 1))
        audit.adjustments.all().delete()
        self.assertEqual(output, history_rows(history_logs(self.emp, 2026, 1)))
        audit.refresh_from_db()
        self.assertEqual(original, (audit.du_lieu_cu, audit.du_lieu_moi))

    def test_views_and_payroll_comparison_do_not_create_summaries(self):
        self.record(nguoi_cap_nhat=self.hr).save()
        self.client.force_login(self.hr)
        response = self.client.get(reverse('bang_cong:employee-month', args=[self.emp.pk]),
                                   {'month': 1, 'year': 2026})
        self.assertEqual(response.status_code, 200)
        summary = payroll_summary(self.emp, self.period)
        self.assertIsNone(summary.pk)
        self.assertFalse(TongHopCong.objects.exists())
        self.assertFalse(LichSuDieuChinhCong.objects.exists())

    def test_approval_links_summary_and_keeps_record_lock(self):
        self.fill_month(self.emp)
        approval = approve_employee(self.hr, self.emp, self.period.pk)
        approval.refresh_from_db()
        self.assertEqual(approval.tong_hop.nhan_vien_id, self.emp.pk)
        self.assertEqual(approval.tong_hop.trang_thai, 'approved')
        with self.assertRaises(ValidationError):
            approve_employee(self.hr, self.emp, self.period.pk)
        row = ChamCong.objects.filter(nhan_vien=self.emp).first()
        row.gio_ra = time(19)
        with self.assertRaises(ValidationError):
            save_record(self.hr, row, 'Blocked')
        self.assertEqual(ChotBangCong.objects.count(), 1)

    def test_period_reopen_updates_summary_without_creating_extra_approvals(self):
        for employee in [self.emp, self.other]:
            self.fill_month(employee)
        change_period(self.director, self.period.pk, 'approve', 'Close')
        self.assertEqual(TongHopCong.objects.filter(trang_thai='approved').count(), 2)
        self.assertFalse(ChotBangCong.objects.filter(tong_hop__isnull=True).exists())
        change_period(self.director, self.period.pk, 'reopen', 'Reopen')
        self.assertEqual(TongHopCong.objects.filter(trang_thai='pending').count(), 2)
        self.assertFalse(ChotBangCong.objects.exists())


class AttendanceSchemaMigrationTests(TransactionTestCase):
    migrate_from = [('attendance', '0007_remove_policy_confirmed')]
    migrate_to = [('attendance', '0008_attendance_summary_and_adjustments')]

    def test_existing_data_is_transferred_and_backfill_is_idempotent(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        apps = executor.loader.project_state(self.migrate_from).apps
        try:
            User = apps.get_model('auth', 'User')
            Employee = apps.get_model('employees', 'Employee')
            Department = apps.get_model('employees', 'Department')
            Period = apps.get_model('attendance', 'AttendancePeriod')
            Record = apps.get_model('attendance', 'AttendanceRecord')
            Audit = apps.get_model('attendance', 'AttendanceAuditLog')
            Approval = apps.get_model('attendance', 'EmployeeAttendanceApproval')
            Day = apps.get_model('attendance', 'WorkCalendarDay')
            user = User.objects.create(username='migration-user')
            department = Department.objects.create(code='MIG', name='Migration')
            employee = Employee.objects.create(user_id=user.pk, code='MIG-01', full_name='Migration',
                department_id=department.pk, hire_date=date(2020, 1, 1), base_salary=10000000)
            period = Period.objects.create(year=2026, month=10, start_time=time(8), lunch_start=time(12),
                lunch_end=time(13), end_time=time(17), standard_hours=8, status='approved')
            Day.objects.create(date=date(2026,10,5), kind='work', expected_units=1)
            row = Record.objects.create(employee_id=employee.pk, date=date(2026,10,5), check_in=time(8),
                check_out=time(19), status='present', work_hours=8, actual_units=1, paid_units=1, updated_by_id=user.pk)
            approval = Approval.objects.create(period_id=period.pk, employee_id=employee.pk, approved_by_id=user.pk)
            audit = Audit.objects.create(actor_id=user.pk, action='edit_record', reason='Historical change',
                before={'check_out':'17:00:00'}, after={'pk':str(row.pk), 'check_out':'19:00:00'})
            before = Record.objects.values().get(pk=row.pk)
            executor = MigrationExecutor(connection)
            executor.migrate(self.migrate_to)
            new_apps = executor.loader.project_state(self.migrate_to).apps
            Record = new_apps.get_model('attendance', 'AttendanceRecord')
            Summary = new_apps.get_model('attendance', 'MonthlyAttendanceSummary')
            Adjustment = new_apps.get_model('attendance', 'AttendanceAdjustment')
            Approval = new_apps.get_model('attendance', 'EmployeeAttendanceApproval')
            current = Record.objects.values().get(pk=row.pk)
            self.assertEqual(before, {key:current[key] for key in before})
            self.assertEqual(current['recorded_overtime_hours'], Decimal(2))
            summary = Summary.objects.get(employee_id=employee.pk, period_id=period.pk)
            self.assertEqual((summary.paid_units, summary.overtime_hours, summary.status), (1, 2, 'approved'))
            self.assertEqual(Approval.objects.get(pk=approval.pk).summary_id, summary.pk)
            self.assertEqual(Adjustment.objects.get(audit_id=audit.pk).new_value, '19:00:00')
            migration = import_module('bang_cong.migrations.0008_attendance_summary_and_adjustments')
            migration.backfill_attendance(new_apps, SimpleNamespace(connection=connection))
            self.assertEqual(Summary.objects.count(), 1)
            self.assertEqual(Adjustment.objects.count(), 1)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
