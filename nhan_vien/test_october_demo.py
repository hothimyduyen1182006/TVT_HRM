from io import StringIO
from django.contrib.auth.models import User
from django.core.management import call_command, CommandError
from unittest.mock import patch
from django.test import TestCase
from bang_cong.models import KyCong, ChamCong
from bang_luong.models import PayrollRecord


class OctoberDemoTests(TestCase):
    def test_single_month_can_reuse_existing_accounts(self):
        user = User.objects.create_user('demo_hr', password='ExistingPasswordForTest')
        password_hash = user.password
        call_command('seed_demo', year=2026, month=10, reuse_users=True, stdout=StringIO())
        user.refresh_from_db()
        self.assertEqual(user.password, password_hash)
        self.assertEqual(user.employee.user_id, user.pk)
        self.assertEqual(list(KyCong.objects.values_list('thang', flat=True)), [10])
        self.assertFalse(ChamCong.objects.exclude(ngay__month=10).exists())
        self.assertEqual(PayrollRecord.objects.count(), 8)
        self.assertEqual(User.objects.filter(username='demo_hr').count(), 1)

    def test_shared_dataset_is_complete_and_reset_preserves_accounts(self):
        from nhan_vien.models import Employee, LaborContract
        from nghi_phep.models import LeaveRequest
        user = User.objects.create_user('existing-admin', password='KeepExistingPassword', is_superuser=True)
        old_hash = user.password
        call_command('seed_october', stdout=StringIO())
        self.assertEqual(Employee.objects.exclude(gender__in=['Nam', 'Nữ']).count(), 0)
        self.assertEqual(LaborContract.objects.count(), 8)
        self.assertEqual(LeaveRequest.objects.count(), 5)
        self.assertEqual(ChamCong.objects.count(), 176)
        self.assertEqual(PayrollRecord.objects.count(), 8)
        with self.assertRaises(CommandError):
            call_command('seed_october', stdout=StringIO())
        before = dict(User.objects.values_list('pk', 'password'))
        with patch('nhan_vien.management.commands.seed_october.Command.backup_database') as backup:
            call_command('seed_october', reset=True, stdout=StringIO())
            backup.assert_called_once()
        self.assertEqual(dict(User.objects.values_list('pk', 'password')), before)
        user.refresh_from_db()
        self.assertEqual(user.password, old_hash)
        self.assertEqual(ChamCong.objects.count(), 176)
