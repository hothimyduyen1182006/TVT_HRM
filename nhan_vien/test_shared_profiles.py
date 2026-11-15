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

from nhan_vien.access import nhan_vien_duoc_hien_thi
from nhan_vien.models import PhongBan, HocVan, NhanVien, HopDongLaoDong, ChucVu
from nhan_vien.management.commands.import_tvt_profiles import Command


class SharedProfileTests(TestCase):
    password = 'Shared-OnlyForTests@2026'

    def run_import(self, **options):
        call_command('import_tvt_profiles', password=self.password, stdout=StringIO(), **options)

    def test_empty_database_import_has_correct_roles_and_no_admin_privileges(self):
        self.run_import()
        self.assertEqual(NhanVien.objects.count(), 8)
        self.assertEqual(get_user_model().objects.count(), 8)
        self.assertEqual(HocVan.objects.count(), 8)
        self.assertEqual(HopDongLaoDong.objects.count(), 8)
        for user in get_user_model().objects.all():
            self.assertTrue(user.check_password(self.password))
            self.assertFalse(user.is_staff)
            self.assertFalse(user.is_superuser)
        director = NhanVien.objects.get(ma_ho_so='NV08')
        self.assertEqual(director.luong_co_ban, 20000000)
        self.assertEqual(director.hop_dong_lao_dong.get().luong_thoa_thuan, 11500000)
        self.assertIsNone(director.chuc_vu)
        self.assertIsNone(director.hop_dong_lao_dong.get().ngay_ket_thuc)
        employee = NhanVien.objects.get(ma_ho_so='NV01')
        self.assertEqual(employee.nguoi_dung.username, 'hothimyduyen')
        self.assertEqual(employee.nguoi_dung.email, 'duyen.marketing@example.com')
        self.assertIn('Khá', employee.hoc_van.get().bang_cap)
        hr = NhanVien.objects.get(ma_ho_so='NV05')
        self.assertEqual(hr.ngay_vao_lam, date(2026, 9, 1))
        self.assertEqual(hr.luong_co_ban, 15000000)
        self.assertEqual(nhan_vien_duoc_hien_thi(employee.nguoi_dung).count(), 1)
        self.assertEqual(nhan_vien_duoc_hien_thi(NhanVien.objects.get(ma_ho_so='NV02').nguoi_dung).count(), 2)
        self.assertEqual(nhan_vien_duoc_hien_thi(hr.nguoi_dung).count(), 8)
        self.assertEqual(nhan_vien_duoc_hien_thi(director.nguoi_dung).count(), 8)

    def test_repeated_import_preserves_ids_passwords_admin_and_existing_files(self):
        admin = get_user_model().objects.create_superuser('existing-admin', password=self.password)
        admin_before = get_user_model().objects.values().get(pk=admin.pk)
        self.run_import()
        employee = NhanVien.objects.get(ma_ho_so='NV01')
        employee.ma_ho_so = 'DEMO-NV01'
        employee.save()
        employee.nguoi_dung.username = 'demo_employee'
        employee.nguoi_dung.save()
        employee.phong_ban.ma_phong_ban = 'DEMO-MKT'
        employee.phong_ban.save()
        education = employee.hoc_van.get()
        education.tep_bang_cap = 'employees/education/existing.pdf'
        education.save()
        contract = employee.hop_dong_lao_dong.get()
        contract.tep_hop_dong = 'employees/contracts/existing.pdf'
        contract.save()
        ids = {model: set(model.objects.values_list('pk', flat=True))
               for model in [NhanVien, PhongBan, ChucVu, HocVan, HopDongLaoDong, get_user_model()]}
        hashes = dict(get_user_model().objects.values_list('pk', 'password'))
        call_command('import_tvt_profiles', password='Different-OnlyForTests@2026', stdout=StringIO())
        self.run_import()
        for model, before in ids.items():
            self.assertEqual(set(model.objects.values_list('pk', flat=True)), before)
        self.assertEqual(dict(get_user_model().objects.values_list('pk', 'password')), hashes)
        self.assertEqual(get_user_model().objects.values().get(pk=admin.pk), admin_before)
        self.assertEqual(NhanVien.objects.get(pk=employee.pk).nguoi_dung.username, 'hothimyduyen')
        self.assertEqual(HocVan.objects.get(pk=education.pk).tep_bang_cap.name, 'employees/education/existing.pdf')
        self.assertEqual(HopDongLaoDong.objects.get(pk=contract.pk).tep_hop_dong.name, 'employees/contracts/existing.pdf')

    def test_reset_changes_only_imported_passwords(self):
        admin = get_user_model().objects.create_superuser('existing-admin', password=self.password)
        original_hash = admin.password
        self.run_import()
        call_command('import_tvt_profiles', password='Replacement-OnlyForTests@2026', reset_passwords=True, stdout=StringIO())
        for employee in NhanVien.objects.select_related('nguoi_dung'):
            self.assertTrue(employee.nguoi_dung.check_password('Replacement-OnlyForTests@2026'))
        admin.refresh_from_db()
        self.assertEqual(admin.password, original_hash)

    def test_username_conflict_is_rejected_without_changes(self):
        self.run_import()
        employee = NhanVien.objects.get(ma_ho_so='NV01')
        employee.nguoi_dung.username = 'legacy-user'
        employee.nguoi_dung.save()
        get_user_model().objects.create_user('hothimyduyen')
        before = list(get_user_model().objects.order_by('pk').values())
        with self.assertRaises(CommandError):
            self.run_import()
        self.assertEqual(list(get_user_model().objects.order_by('pk').values()), before)

    def test_validation_failure_rolls_back_all_prior_creations(self):
        user = get_user_model().objects.create_user('unrelated')
        department = PhongBan.objects.create(ma_phong_ban='OTHER', ten_phong_ban='Phòng khác')
        employee = NhanVien.objects.create(nguoi_dung=user, ma_ho_so='OTHER', ho_va_ten='Người khác',
            phong_ban=department, so_dien_thoai='0905123404', ngay_vao_lam=date(2020, 1, 1), luong_co_ban=0)
        before = NhanVien.objects.values().get(pk=employee.pk)
        with self.assertRaises(CommandError):
            self.run_import()
        self.assertEqual(NhanVien.objects.count(), 1)
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(PhongBan.objects.count(), 1)
        self.assertFalse(HocVan.objects.exists())
        self.assertFalse(HopDongLaoDong.objects.exists())
        self.assertEqual(NhanVien.objects.values().get(pk=employee.pk), before)

    def test_dry_run_needs_no_password_and_writes_nothing(self):
        with patch('nhan_vien.management.commands.import_tvt_profiles.getpass.getpass', side_effect=AssertionError):
            call_command('import_tvt_profiles', dry_run=True, stdout=StringIO())
        self.assertFalse(NhanVien.objects.exists())
        self.assertFalse(get_user_model().objects.exists())
        self.assertFalse(PhongBan.objects.exists())

    def test_privileged_account_cannot_be_reused(self):
        get_user_model().objects.create_superuser('hothimyduyen', password=self.password)
        with self.assertRaises(CommandError):
            self.run_import()
        self.assertFalse(NhanVien.objects.exists())

    def test_shared_payload_contains_no_credentials_or_private_file_paths(self):
        payload = json.loads((Path(__file__).resolve().parent / 'data' / 'tvt_profiles.json').read_text(encoding='utf-8'))
        for item in payload['employees']:
            for field in ['password', 'cccd', 'hinh_anh', 'is_staff', 'is_superuser', 'last_login']:
                self.assertNotIn(field, item)
            for education in item['educations']:
                self.assertNotIn('tep_bang_cap', education)
            for contract in item['contracts']:
                self.assertNotIn('tep_hop_dong', contract)


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
