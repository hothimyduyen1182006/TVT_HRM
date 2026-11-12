"""Verify the rename preserves historical data and granted permissions."""
from datetime import date, time

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class VietnameseNamesMigrationTests(TransactionTestCase):
    def test_existing_records_and_permissions_keep_their_identity(self):
        old_target = [('attendance', '0008_attendance_summary_and_adjustments')]
        try:
            call_command('migrate', 'attendance', old_target[0][1], verbosity=0, interactive=False)
            old_apps = MigrationExecutor(connection).loader.project_state(old_target).apps
            user = old_apps.get_model('auth', 'User').objects.create(username='rename-test')
            department = old_apps.get_model('employees', 'Department').objects.create(code='RENAME', name='Production')
            employee = old_apps.get_model('employees', 'Employee').objects.create(
                user_id=user.pk, code='RENAME-01', full_name='Rename test', department_id=department.pk,
                hire_date=date(2020, 1, 1), base_salary=10000000,
            )
            period = old_apps.get_model('attendance', 'AttendancePeriod').objects.create(
                month=10, year=2026, start_time=time(8), lunch_start=time(12), lunch_end=time(13),
                end_time=time(17), standard_hours=8,
            )
            old_apps.get_model('attendance', 'WorkCalendarDay').objects.create(
                date=date(2026, 10, 5), kind='work', expected_units=1,
            )
            record = old_apps.get_model('attendance', 'AttendanceRecord').objects.create(
                employee_id=employee.pk, date=date(2026, 10, 5), check_in=time(8), check_out=time(19),
                status='present', work_hours=8, actual_units=1, paid_units=1,
                recorded_overtime_hours=2, updated_by_id=user.pk,
            )
            historical_json = {'pk': str(record.pk), 'check_out': '19:00:00', 'paid_units': '1.0000'}
            audit = old_apps.get_model('attendance', 'AttendanceAuditLog').objects.create(
                actor_id=user.pk, action='edit_record', reason='Historical audit',
                before={'check_out': '17:00:00'}, after=historical_json,
            )
            permission = old_apps.get_model('auth', 'Permission').objects.get(
                content_type__app_label='attendance', codename='change_attendancerecord',
            )
            group = old_apps.get_model('auth', 'Group').objects.create(name='Rename test group')
            group.permissions.add(permission)
            user.user_permissions.add(permission)
            permission_id, content_type_id = permission.pk, permission.content_type_id

            call_command('migrate', 'attendance', '0009_vietnamese_attendance_names', verbosity=0, interactive=False)
            from .models import ChamCong, KyCong, NhatKyCong
            from django.contrib.auth.models import Group, Permission, User
            current = ChamCong.objects.get(pk=record.pk)
            self.assertEqual((current.nhan_vien_id, current.ngay, current.gio_vao, current.gio_ra),
                             (employee.pk, date(2026, 10, 5), time(8), time(19)))
            self.assertEqual((current.tong_cong, current.so_gio_tang_ca, current.gio_tang_ca), (1, 2, 2))
            self.assertEqual(str(KyCong.objects.get(pk=period.pk)), '10/2026')
            self.assertEqual(NhatKyCong.objects.get(pk=audit.pk).du_lieu_moi, historical_json)
            renamed_permission = Permission.objects.get(pk=permission_id)
            self.assertEqual(renamed_permission.codename, 'change_chamcong')
            self.assertEqual(renamed_permission.content_type_id, content_type_id)
            self.assertTrue(Group.objects.get(pk=group.pk).permissions.filter(pk=permission_id).exists())
            self.assertTrue(User.objects.get(pk=user.pk).user_permissions.filter(pk=permission_id).exists())
        finally:
            call_command('migrate', verbosity=0, interactive=False)
