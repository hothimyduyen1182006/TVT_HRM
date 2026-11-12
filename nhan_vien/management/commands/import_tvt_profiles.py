"""Import the explicitly shared employee profiles without shipping credentials or a database."""
import getpass
import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.db.models import Q

from nhan_vien.models import Department, Education, Employee, LaborContract, Position


class Command(BaseCommand):
    help = 'Nhập 8 hồ sơ/tài khoản TVT đã chia sẻ; giữ dữ liệu khác, không tính hoặc chi trả lương.'

    def add_arguments(self, parser):
        parser.add_argument('--password', help='Mật khẩu cho tài khoản mới; bỏ qua để nhập ẩn khi được hỏi.')
        parser.add_argument('--reset-passwords', action='store_true', help='Đặt lại mật khẩu của 8 tài khoản trong bộ dữ liệu.')
        parser.add_argument('--dry-run', action='store_true', help='Kiểm tra toàn bộ rồi hoàn tác, không ghi dữ liệu.')

    def handle(self, *args, **options):
        payload = json.loads((Path(__file__).resolve().parents[2] / 'data' / 'tvt_profiles.json').read_text(encoding='utf-8'))
        if payload.get('schema_version') != 1 or len(payload.get('employees', [])) != 8:
            raise CommandError('Bộ dữ liệu không đúng định dạng hoặc thiếu hồ sơ.')
        self.User = get_user_model()
        self.dry_run = options['dry_run']
        self.reset = options['reset_passwords']
        self.password = options.get('password')
        try:
            for item in payload['employees']:
                self._account(item)  # Check conflicts before asking for credentials or writing anything.
                if not set(item['roles']) <= {'Nhân viên', 'Trưởng phòng', 'Nhân sự', 'Giám đốc'}:
                    raise CommandError('Bộ dữ liệu chứa vai trò không được phép.')
            needs_password = self.reset or any(self._account(item)[1] is None for item in payload['employees'])
            if needs_password and not self.password and not self.dry_run:
                self.password = getpass.getpass('Mật khẩu cho các tài khoản được tạo/đặt lại: ')
                if self.password != getpass.getpass('Nhập lại mật khẩu: '):
                    raise CommandError('Hai lần nhập mật khẩu không khớp.')
            if needs_password and not self.dry_run:
                validate_password(self.password or '')
            if not self.dry_run:
                self._backup()
            with transaction.atomic():
                departments = {}
                for item in payload['departments']:
                    matches = Department.objects.filter(code__in=[item['code'], 'DEMO-' + item['code']])
                    if matches.count() > 1:
                        raise CommandError('Có cả mã phòng cũ và mới: ' + item['code'])
                    department = matches.first() or Department()
                    department.code, department.name = item['code'], item['name']
                    department.full_clean()
                    department.save()
                    departments[item['code']] = department
                people = {}
                for item in payload['employees']:
                    people[item['code']] = self._profile(item, departments[item['department_code']])
                for item in payload['departments']:
                    if item['manager_code']:
                        department = departments[item['code']]
                        manager = people[item['manager_code']]
                        if manager.department_id != department.pk:
                            raise CommandError('Trưởng phòng phải thuộc đúng phòng ban.')
                        department.manager = manager
                        department.save(update_fields=['manager'])
                if self.dry_run:
                    transaction.set_rollback(True)
        except (ValidationError, IntegrityError) as error:
            detail = '; '.join(error.messages) if isinstance(error, ValidationError) else 'Trùng mã hoặc thông tin duy nhất.'
            raise CommandError(detail) from error
        self.stdout.write(self.style.SUCCESS(
            'Kiểm tra thành công; chưa ghi dữ liệu.' if self.dry_run else 'Đã nhập 8 hồ sơ, tài khoản, bằng cấp và hợp đồng.'))
        self.stdout.write('Không thay đổi tài khoản quản trị, dữ liệu công/lương hoặc tài liệu đính kèm hiện có.')
        if not self.reset:
            self.stdout.write('Mật khẩu của tài khoản đã có được giữ nguyên.')

    def _account(self, item):
        matches = Employee.objects.filter(code__in=[item['code'], 'DEMO-' + item['code']]).select_related('user')
        if matches.count() > 1:
            raise CommandError('Có cả mã nhân viên cũ và mới: ' + item['code'])
        employee = matches.first()
        targets = self.User.objects.filter(username__iexact=item['username'])
        if targets.count() > 1:
            raise CommandError('Nhiều tài khoản có tên tương tự: ' + item['username'])
        target = targets.first()
        user = employee.user if employee else target
        if employee and target and target.pk != employee.user_id:
            raise CommandError('Tên đăng nhập đã thuộc tài khoản khác: ' + item['username'])
        if not employee and target and Employee.objects.filter(user=target).exists():
            raise CommandError('Tài khoản đã liên kết nhân viên khác: ' + item['username'])
        if user and (user.is_staff or user.is_superuser):
            raise CommandError('Không cập nhật tài khoản quản trị: ' + item['username'])
        return employee, user

    def _profile(self, item, department):
        employee, user = self._account(item)
        is_new = user is None
        user = user or self.User()
        for field in ['username', 'first_name', 'last_name', 'email']:
            setattr(user, field, item[field])
        user.is_active = item['account_active']
        if is_new or self.reset:
            if self.dry_run and not self.password:
                user.set_unusable_password()
            else:
                validate_password(self.password or '', user=user)
                user.set_password(self.password)
        user.full_clean()
        user.save()
        user.groups.set([Group.objects.get_or_create(name=name)[0] for name in item['roles']])
        employee = employee or Employee(user=user)
        for field in ['code', 'full_name', 'gender', 'phone', 'address', 'is_active', 'employment_status']:
            setattr(employee, field, item[field])
        employee.date_of_birth = date.fromisoformat(item['date_of_birth']) if item['date_of_birth'] else None
        employee.hire_date = date.fromisoformat(item['hire_date'])
        from bang_cong.models import AttendanceRecord
        if AttendanceRecord.objects.filter(employee_id=employee.pk, date__lt=employee.hire_date).exists():
            raise CommandError('Ngày vào làm xung đột với chấm công: ' + item['code'])
        employee.base_salary = Decimal(item['base_salary'])
        employee.department = department
        if item['position']:
            position, _ = Position.objects.get_or_create(department=department, name=item['position']['name'],
                defaults={'salary_coefficient': Decimal(item['position']['salary_coefficient'])})
            position.full_clean()
            employee.position = position
        else:
            employee.position = None
        employee.full_clean()
        employee.save()
        for values in item['educations']:
            education = Education.objects.filter(code=values['code']).first()
            if education and education.employee_id != employee.pk:
                raise CommandError('Mã bằng cấp đã thuộc nhân viên khác: ' + values['code'])
            if not education:
                matches = Education.objects.filter(employee=employee, major=values['major'], school=values['school'],
                    graduation_year=values['graduation_year'])
                if matches.count() > 1:
                    raise CommandError('Nhiều bằng cấp trùng thông tin: ' + item['code'])
                education = matches.first() or Education(employee=employee)
            for field, value in values.items():
                setattr(education, field, value)
            education.full_clean()
            education.save()
        for values in item['contracts']:
            matches = LaborContract.objects.filter(Q(code=values['code']) | Q(number=values['number']))
            if matches.count() > 1 or matches.exclude(employee=employee).exists():
                raise CommandError('Mã/số hợp đồng bị trùng: ' + values['code'])
            contract = matches.first() or LaborContract(employee=employee)
            for field, value in values.items():
                if field in ['signed_date', 'start_date', 'end_date']:
                    value = date.fromisoformat(value) if value else None
                elif field == 'agreed_salary':
                    value = Decimal(value)
                setattr(contract, field, value)
            contract.full_clean()
            contract.save()
        return employee

    def _backup(self):
        config = settings.DATABASES['default']
        name = str(config['NAME'])
        if config['ENGINE'] != 'django.db.backends.sqlite3' or name == ':memory:' or name.startswith('file:memorydb_'):
            return
        database = Path(name).resolve()
        if not database.is_file():
            return
        directory = Path(settings.BASE_DIR) / '.local-backups'
        directory.mkdir(exist_ok=True)
        destination = directory / ('before-import-profiles-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
        source_connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
        backup_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(backup_connection)
        finally:
            backup_connection.close()
            source_connection.close()
        self.stdout.write('Đã sao lưu database vào .local-backups/' + destination.name)
