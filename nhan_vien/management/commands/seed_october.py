"""Bộ dữ liệu đồ án tháng 10/2026; không chia sẻ database hoặc mật khẩu hiện có."""
from datetime import date
from io import StringIO
from pathlib import Path
import secrets
import sqlite3
from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import BaseCommand, CommandError, call_command
from django.db import connection, transaction
from django.utils import timezone
from nhan_vien.models import NhanVien, PhongBan, ChucVu, HopDongLaoDong
from nghi_phep.models import NgayNghi, DonNghiPhep
from thuong.models import Bonus
from .seed_demo import PEOPLE


class Command(BaseCommand):
    help = 'Tạo bộ demo tháng 10/2026; --reset xóa nghiệp vụ sau khi sao lưu, giữ tài khoản hiện có.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Xóa toàn bộ dữ liệu nghiệp vụ cũ trước khi tạo; giữ tài khoản.')

    def backup_database(self):
        if connection.vendor != 'sqlite':
            raise CommandError('Lệnh --reset chỉ hỗ trợ SQLite. Hãy sao lưu bằng công cụ database đang dùng.')
        folder = Path(settings.BASE_DIR) / '.local-backups'
        folder.mkdir(exist_ok=True)
        backup = folder / ('db-before-seed-october-' + timezone.localtime().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
        connection.ensure_connection()
        with sqlite3.connect(backup) as target:
            connection.connection.backup(target)
        self.stdout.write(f'Backup: {backup}')

    def handle(self, *args, **options):
        business_apps = ['employees', 'attendance', 'payroll', 'leaves', 'bonuses']
        has_data = any(model.objects.exists() for app in business_apps for model in apps.get_app_config(app).get_models())
        if has_data and not options['reset']:
            raise CommandError('Đã có dữ liệu nghiệp vụ. Muốn thay toàn bộ bằng demo tháng 10/2026, chạy seed_october --reset. Tài khoản/mật khẩu hiện có sẽ được giữ nguyên.')
        if has_data:
            self.backup_database()
        existing = dict(User.objects.values_list('pk', 'password'))
        existing_roles = {u.pk: set(u.groups.values_list('pk', flat=True)) for u in User.objects.all()}
        new_names = [person[0] for person in PEOPLE if not User.objects.filter(username=person[0]).exists()]
        password = secrets.token_urlsafe(16)
        if apps.get_model('attendance', 'LichSuTangCa').objects.exists():
            raise CommandError('Không thể đặt lại dữ liệu vì cần bảo toàn lịch sử OT.')
        with transaction.atomic():
            order = ['payroll.PayrollExportLog', 'payroll.PayrollAuditLog', 'payroll.Luong',
                'payroll.PayrollAdjustment', 'payroll.PayrollInput', 'payroll.PayrollPeriod',
                'attendance.ChotBangCong',
                'attendance.LichSuTangCa', 'attendance.ChamCong', 'leaves.NgayNghi',
                'leaves.DonNghiPhep', 'bonuses.Bonus', 'attendance.KyCong',
                'employees.Education', 'employees.LaborContract']
            for label in order:
                apps.get_model(label).objects.all().delete()
            PhongBan.objects.update(truong_phong=None)
            NhanVien.objects.all().delete()
            ChucVu.objects.all().delete()
            PhongBan.objects.all().delete()
            call_command('seed_demo', year=2026, month=10, reuse_users=True, password=password, stdout=StringIO())
            call_command('seed_positions', stdout=StringIO())
            hr = User.objects.get(username='demo_hr')
            director = User.objects.get(username='demo_director')
            for index, employee in enumerate(NhanVien.objects.select_related('phong_ban', 'nguoi_dung').order_by('ma_ho_so')):
                employee.gioi_tinh = 'Nam' if index in [0, 1, 2, 5, 7] else 'Nữ'
                if employee.nguoi_dung.groups.filter(name='Trưởng phòng').exists():
                    employee.chuc_vu = ChucVu.objects.filter(phong_ban=employee.phong_ban, ten_chuc_vu__startswith='Trưởng phòng').first()
                elif employee.nguoi_dung == director:
                    employee.chuc_vu, _ = ChucVu.objects.get_or_create(phong_ban=employee.phong_ban, ten_chuc_vu='Giám đốc', defaults={'he_so_luong_chuc_vu': 1})
                employee.save(update_fields=['gioi_tinh', 'chuc_vu'])
                HopDongLaoDong.objects.create(ho_so_ca_nhan=employee, ma_hop_dong=f'DEMO-HD-{index+1:02}', so_hop_dong=f'DEMO/2026/10/{index+1:02}',
                    loai_hop_dong='Hợp đồng minh họa 12 tháng', ngay_ky=date(2026, 10, 1), ngay_bat_dau=date(2026, 10, 1),
                    ngay_ket_thuc=date(2027, 9, 30), luong_thoa_thuan=employee.luong_co_ban, trang_thai='Đang hiệu lực')
            Bonus.objects.update(proposed_by=hr)
            # Chỉ so sánh tài khoản cũ, không in hash hoặc mật khẩu hiện có.
            if dict(User.objects.filter(pk__in=existing).values_list('pk', 'password')) != existing:
                raise CommandError('Tài khoản cũ bị thay đổi; đã hoàn tác toàn bộ thao tác.')
            for user in User.objects.filter(pk__in=existing_roles):
                user.groups.set(existing_roles[user.pk])
        self.stdout.write(self.style.SUCCESS('Đã tạo demo 10/2026: 8 nhân viên, 7 phòng ban, 176 bản ghi công, 8 phiếu lương, OT, thưởng, nghỉ phép, chức vụ và hợp đồng. Lương đã trả là mô phỏng.'))
        self.stdout.write('Chọn tháng 10/2026 trên giao diện. Tài khoản và mật khẩu hiện có được giữ nguyên.')
        if new_names:
            self.stdout.write('Tài khoản mới: ' + ', '.join(new_names))
            self.stdout.write('Mật khẩu CHỈ cho tài khoản mới: ' + password)
