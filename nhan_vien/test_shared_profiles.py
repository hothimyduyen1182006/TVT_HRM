import json
import sqlite3
from contextlib import closing
from datetime import date
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.test import TestCase, SimpleTestCase

from nhan_vien.access import visible_employees
from nhan_vien.models import Department, Education, Employee, LaborContract, Position
from nhan_vien.management.commands.import_tvt_profiles import Command


class SharedProfileTests(TestCase):
    password = 'Shared-OnlyForTests@2026'

    def run_import(self, **options):
        call_command('import_tvt_profiles', password=self.password, stdout=StringIO(), **options)

    def test_empty_database_import_has_correct_roles_and_no_admin_privileges(self):
        self.run_import()
        self.assertEqual(Employee.objects.count(), 8)
        self.assertEqual(get_user_model().objects.count(), 8)
        self.assertEqual(Education.objects.count(), 8)
        self.assertEqual(LaborContract.objects.count(), 8)
        for user in get_user_model().objects.all():
            self.assertTrue(user.check_password(self.password))
            self.assertFalse(user.is_staff)
            self.assertFalse(user.is_superuser)
        director = Employee.objects.get(code='NV08')
        self.assertEqual(director.base_salary, 20000000)
        self.assertEqual(director.contracts.get().agreed_salary, 11500000)
        self.assertIsNone(director.position)
        self.assertIsNone(director.contracts.get().end_date)
        employee = Employee.objects.get(code='NV01')
        self.assertEqual(employee.user.username, 'hothimyduyen')
        self.assertEqual(employee.user.email, 'duyen.marketing@example.com')
        self.assertIn('Khá', employee.educations.get().degree)
        hr = Employee.objects.get(code='NV05')
        self.assertEqual(hr.hire_date, date(2026, 9, 1))
        self.assertEqual(hr.base_salary, 15000000)
        self.assertEqual(visible_employees(employee.user).count(), 1)
        self.assertEqual(visible_employees(Employee.objects.get(code='NV02').user).count(), 2)
        self.assertEqual(visible_employees(hr.user).count(), 8)
        self.assertEqual(visible_employees(director.user).count(), 8)

    def test_repeated_import_preserves_ids_passwords_admin_and_existing_files(self):
        admin = get_user_model().objects.create_superuser('existing-admin', password=self.password)
        admin_before = get_user_model().objects.values().get(pk=admin.pk)
        self.run_import()
        employee = Employee.objects.get(code='NV01')
        employee.code = 'DEMO-NV01'
        employee.save()
        employee.user.username = 'demo_employee'
        employee.user.save()
        employee.department.code = 'DEMO-MKT'
        employee.department.save()
        education = employee.educations.get()
        education.certificate_file = 'employees/education/existing.pdf'
        education.save()
        contract = employee.contracts.get()
        contract.contract_file = 'employees/contracts/existing.pdf'
        contract.save()
        ids = {model: set(model.objects.values_list('pk', flat=True))
               for model in [Employee, Department, Position, Education, LaborContract, get_user_model()]}
        hashes = dict(get_user_model().objects.values_list('pk', 'password'))
        call_command('import_tvt_profiles', password='Different-OnlyForTests@2026', stdout=StringIO())
        self.run_import()
        for model, before in ids.items():
            self.assertEqual(set(model.objects.values_list('pk', flat=True)), before)
        self.assertEqual(dict(get_user_model().objects.values_list('pk', 'password')), hashes)
        self.assertEqual(get_user_model().objects.values().get(pk=admin.pk), admin_before)
        self.assertEqual(Employee.objects.get(pk=employee.pk).user.username, 'hothimyduyen')
        self.assertEqual(Education.objects.get(pk=education.pk).certificate_file.name, 'employees/education/existing.pdf')
        self.assertEqual(LaborContract.objects.get(pk=contract.pk).contract_file.name, 'employees/contracts/existing.pdf')

    def test_reset_changes_only_imported_passwords(self):
        admin = get_user_model().objects.create_superuser('existing-admin', password=self.password)
        original_hash = admin.password
        self.run_import()
        call_command('import_tvt_profiles', password='Replacement-OnlyForTests@2026', reset_passwords=True, stdout=StringIO())
        for employee in Employee.objects.select_related('user'):
            self.assertTrue(employee.user.check_password('Replacement-OnlyForTests@2026'))
        admin.refresh_from_db()
        self.assertEqual(admin.password, original_hash)

    def test_username_conflict_is_rejected_without_changes(self):
        self.run_import()
        employee = Employee.objects.get(code='NV01')
        employee.user.username = 'legacy-user'
        employee.user.save()
        get_user_model().objects.create_user('hothimyduyen')
        before = list(get_user_model().objects.order_by('pk').values())
        with self.assertRaises(CommandError):
            self.run_import()
        self.assertEqual(list(get_user_model().objects.order_by('pk').values()), before)

    def test_validation_failure_rolls_back_all_prior_creations(self):
        user = get_user_model().objects.create_user('unrelated')
        department = Department.objects.create(code='OTHER', name='Phòng khác')
        employee = Employee.objects.create(user=user, code='OTHER', full_name='Người khác',
            department=department, phone='0905123404', hire_date=date(2020, 1, 1), base_salary=0)
        before = Employee.objects.values().get(pk=employee.pk)
        with self.assertRaises(CommandError):
            self.run_import()
        self.assertEqual(Employee.objects.count(), 1)
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(Department.objects.count(), 1)
        self.assertFalse(Education.objects.exists())
        self.assertFalse(LaborContract.objects.exists())
        self.assertEqual(Employee.objects.values().get(pk=employee.pk), before)

    def test_dry_run_needs_no_password_and_writes_nothing(self):
        with patch('nhan_vien.management.commands.import_tvt_profiles.getpass.getpass', side_effect=AssertionError):
            call_command('import_tvt_profiles', dry_run=True, stdout=StringIO())
        self.assertFalse(Employee.objects.exists())
        self.assertFalse(get_user_model().objects.exists())
        self.assertFalse(Department.objects.exists())

    def test_privileged_account_cannot_be_reused(self):
        get_user_model().objects.create_superuser('hothimyduyen', password=self.password)
        with self.assertRaises(CommandError):
            self.run_import()
        self.assertFalse(Employee.objects.exists())

    def test_shared_payload_contains_no_credentials_or_private_file_paths(self):
        payload = json.loads((Path(__file__).resolve().parent / 'data' / 'tvt_profiles.json').read_text(encoding='utf-8'))
        for item in payload['employees']:
            for field in ['password', 'national_id', 'avatar', 'is_staff', 'is_superuser', 'last_login']:
                self.assertNotIn(field, item)
            for education in item['educations']:
                self.assertNotIn('certificate_file', education)
            for contract in item['contracts']:
                self.assertNotIn('contract_file', contract)


class SharedProfileBackupTests(SimpleTestCase):
    def test_sqlite_backup_is_readable_and_matches_source(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / 'source.sqlite3'
            with closing(sqlite3.connect(database)) as connection:
                with connection:
                    connection.execute('CREATE TABLE example (value TEXT)')
                    connection.execute("INSERT INTO example VALUES ('retained')")
            config = SimpleNamespace(BASE_DIR=root, DATABASES={'default': {
                'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(database)}})
            command = Command(stdout=StringIO())
            with patch('nhan_vien.management.commands.import_tvt_profiles.settings', config):
                command._backup()
            backups = list((root / '.local-backups').glob('*.sqlite3'))
            self.assertEqual(len(backups), 1)
            with closing(sqlite3.connect(backups[0])) as connection:
                self.assertEqual(connection.execute('SELECT value FROM example').fetchone()[0], 'retained')
