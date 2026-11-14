"""Dữ liệu minh họa độc lập; chỉ chạy khi chưa có nhân viên nghiệp vụ."""
import calendar
import secrets
from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from nhan_vien.models import Department, Employee
from bang_cong.models import KyCong, ChamCong, LichLamViec
from bang_cong.services.quy_trinh import luu_cham_cong, xu_ly_trang_thai_ky_cong
from nghi_phep.models import LeaveDay
from thuong.models import Bonus
from bang_luong.models import PayrollPeriod, PayrollInput, PayrollAdjustment
from bang_luong.services.tinh_toan import tinh_bang_luong
from bang_luong.services.quy_trinh import xu_ly_trang_thai_luong


PEOPLE = [
    ('demo_employee', 'Nguyễn An (DEMO)', 'MKT', 'Marketing', '9500000', 'Nhân viên'),
    ('demo_manager', 'Trần Minh (DEMO)', 'SX', 'Sản xuất', '7000000', 'Trưởng phòng'),
    ('demo_nv03', 'Lê Duy (DEMO)', 'SX', 'Sản xuất', '7800000', 'Nhân viên'),
    ('demo_nv04', 'Phạm Nhi (DEMO)', 'TK', 'Thiết kế', '12000000', 'Nhân viên'),
    ('demo_hr', 'Võ Na (DEMO)', 'NS', 'Nhân sự', '9000000', 'Nhân sự'),
    ('demo_nv06', 'Đặng Huy (DEMO)', 'IT', 'IT', '15000000', 'Nhân viên'),
    ('demo_nv07', 'Bùi Nam (DEMO)', 'KD', 'Kinh doanh', '10000000', 'Nhân viên'),
    ('demo_director', 'Nguyễn Thanh (DEMO)', 'TC', 'Tài chính', '18000000', 'Giám đốc'),
]


class Command(BaseCommand):
    help = 'Tạo bộ demo 8 nhân viên, 3 kỳ 09/10/11; không ghi đè dữ liệu có sẵn.'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, default=2026)
        parser.add_argument('--month', type=int, choices=range(1, 13), help='Chỉ tạo một tháng cụ thể.')
        parser.add_argument('--reuse-users', action='store_true', help='Giữ tài khoản demo và mật khẩu khi chưa có dữ liệu nhân viên.')
        parser.add_argument('--password', help='Mật khẩu chỉ dành cho tài khoản demo mới; bỏ trống để sinh ngẫu nhiên.')

    @transaction.atomic
    def handle(self, *args, **options):
        year = options['year']
        months = [options['month']] if options.get('month') else [9, 10, 11]
        reuse_users = options.get('reuse_users', False)
        if not 2001 <= year <= 2099:
            raise CommandError('Year must be between 2001 and 2099.')
        codes = [f'DEMO-NV{index:02}' for index in range(1, len(PEOPLE) + 1)]
        usernames = [person[0] for person in PEOPLE]
        User = get_user_model()
        if (Employee.objects.filter(code__in=codes).count() == len(codes)
                and User.objects.filter(username__in=usernames).count() == len(usernames)
                and KyCong.objects.filter(nam=year, thang__in=months).count() == len(months)):
            self.stdout.write('Demo already exists. No data or passwords were changed.')
            return
        if Employee.objects.exists():
            raise CommandError('Employees already exist. Demo seeding requires an empty employee database; nothing changed.')
        if (not reuse_users and User.objects.filter(username__in=usernames).exists()) or Department.objects.filter(code__startswith='DEMO-').exists():
            raise CommandError('Demo account/department names already exist; nothing changed.')
        if (KyCong.objects.filter(nam=year, thang__in=months).exists()
                or LichLamViec.objects.filter(ngay__year=year, ngay__month__in=months).exists()):
            raise CommandError('Target periods/calendar already exist; nothing changed.')
        password = options.get('password') or secrets.token_urlsafe(12)
        if len(password) < 12:
            raise CommandError('Use at least 12 characters for demo passwords.')
        users, employees, departments = {}, [], {}
        for index, (username, name, code, department, salary, role) in enumerate(PEOPLE, 1):
            if code not in departments:
                departments[code] = Department.objects.create(code='DEMO-' + code, name=f'Phòng {department} (DEMO)',
                    allows_overtime=False)
            user = User.objects.filter(username=username).first() if reuse_users else None
            if user is None:
                user = User.objects.create_user(username=username, password=password,
                                                first_name='DEMO', last_name=name.replace(' (DEMO)', ''))
            user.groups.add(Group.objects.get_or_create(name=role)[0])
            users[username] = user
            employee = Employee(code=f'DEMO-NV{index:02}', full_name=name, user=user, department=departments[code],
                                hire_date=date(year - 1, 1, 1), base_salary=Decimal(salary))
            employee.full_clean()
            employee.save()
            employees.append(employee)
        departments['SX'].manager = employees[1]
        departments['SX'].save(update_fields=['manager'])
        hr, director = users['demo_hr'], users['demo_director']
        for month in months:
            period = KyCong(nam=year, thang=month, gio_bat_dau=time(8), bat_dau_nghi_trua=time(12),
                ket_thuc_nghi_trua=time(13), gio_ket_thuc=time(17), gio_chuan=Decimal(8))
            period.full_clean()
            period.save()
            workdays, restdays = [], []
            for number in range(1, calendar.monthrange(year, month)[1] + 1):
                day = date(year, month, number)
                # Lịch minh họa do bộ demo lựa chọn; không phải chính sách chính thức.
                holiday = month == 9 and number == 2
                kind = 'holiday' if holiday else ('work' if day.weekday() < 5 else 'rest')
                schedule = LichLamViec(ngay=day, loai_ngay=kind, cong_chuan=1 if kind == 'work' else 0,
                                           ghi_chu='DEMO: lịch minh họa, không dùng cho lương thật')
                schedule.full_clean()
                schedule.save()
                if kind == 'work':
                    workdays.append(day)
                elif kind == 'rest':
                    restdays.append(day)
            for index, employee in enumerate(employees):
                for number, day in enumerate(workdays):
                    values = {'nhan_vien': employee, 'ngay': day, 'trang_thai': 'present',
                              'gio_vao': time(8), 'gio_ra': time(17), 'ghi_chu': 'DEMO: dữ liệu minh họa'}
                    if index in [2, 3, 5] and number == 2:
                        self.leave(employee, day, Decimal(1), True)
                        values.update(trang_thai='leave', gio_vao=None, gio_ra=None, ghi_chu='DEMO: nghỉ phép hưởng lương')
                    elif index == 4 and number == 3:
                        self.leave(employee, day, Decimal(1), False)
                        values.update(trang_thai='leave', gio_vao=None, gio_ra=None, ghi_chu='DEMO: nghỉ không lương')
                    elif index in [2, 6] and number == 4:
                        values.update(trang_thai='absent', gio_vao=None, gio_ra=None, ghi_chu='DEMO: nghỉ không phép đã xác nhận')
                    elif index == 3 and number == 6:
                        self.leave(employee, day, Decimal(1), True)
                        values.update(
                            trang_thai='leave',
                            gio_vao=None,
                            gio_ra=None,
                            ghi_chu='DEMO: nghỉ phép hưởng lương trọn ngày',
                        )
                    elif index in [1, 2, 4, 6] and number in [0, 5]:
                        values['gio_vao'] = time(8, 10 + index * 5)
                    row = luu_cham_cong(hr, ChamCong(**values), 'DEMO: nhập dữ liệu chấm công minh họa')
                    if index == 2 and number == 0:
                        row.gio_vao = time(8, 10)
                        luu_cham_cong(hr, row, 'DEMO: sửa giờ vào sau khi đối chiếu; xem giá trị trước/sau trong lịch sử')
                for approved in [True, False]:
                    bonus = Bonus(employee=employee, month=month, year=year,
                        name='DEMO: thưởng đã duyệt' if approved else 'DEMO: thưởng chưa duyệt - không tính lương',
                        amount=Decimal(300000 + index * 50000) if approved else Decimal(2000000),
                        bonus_type='other', reason='DEMO: Lý do minh họa cho đề xuất thưởng khác.',
                        proposed_at=timezone.now(),
                        status='approved' if approved else 'pending', approved_by=director if approved else None,
                        approved_at=timezone.now() if approved else None)
                    bonus.full_clean()
                    bonus.save()
            xu_ly_trang_thai_ky_cong(director, period.pk, 'approve', 'DEMO: duyệt kỳ công minh họa; không phải dữ liệu thực tế')
            payroll, _ = PayrollPeriod.objects.get_or_create(attendance_period=period)
            for index, employee in enumerate(employees):
                inputs = PayrollInput(period=payroll, employee=employee, insurance_base=employee.base_salary,
                    insurance_rates={'BHXH': '0.08', 'BHYT': '0.015', 'BHTN': '0.01'},
                    tax_amount=Decimal(0 if index < 3 else index * 50000),
                    tax_basis='DEMO: số thuế giả lập theo kỳ để thử giao diện, không phải kết quả tính thuế thực tế.',
                    insurance_basis='DEMO: tỷ lệ và lương đóng BH chỉ là dữ liệu minh họa, không phải chính sách chính thức.',
                    verified=True)
                inputs.full_clean()
                inputs.save()
                PayrollAdjustment.objects.create(period=payroll, employee=employee, kind='allowance',
                    name='DEMO: phụ cấp ăn trưa', amount=Decimal(450000), basis='DEMO: phụ cấp minh họa đã duyệt', approved=True)
                if index == 6:
                    PayrollAdjustment.objects.create(period=payroll, employee=employee, kind='deduction',
                        name='DEMO: hoàn ứng', amount=Decimal(100000), basis='DEMO: khấu trừ minh họa, không phải phạt đi trễ', approved=True)
            tinh_bang_luong(hr, payroll.pk, 'DEMO: tính bảng lương minh họa bằng service hiện có')
            if month in [9, 10]:
                xu_ly_trang_thai_luong(director, payroll.pk, 'approve', 'DEMO: duyệt bảng lương minh họa')
            if month == 10:
                xu_ly_trang_thai_luong(director, payroll.pk, 'paid', 'DEMO: mô phỏng trạng thái đã trả, không có giao dịch thật',
                               f'DEMO-PAY-{year}-10: chứng từ giả lập để thử giao diện, không chuyển tiền thật')
            if month == 11:
                xu_ly_trang_thai_ky_cong(director, period.pk, 'reopen',
                              'DEMO: chuẩn bị kỳ công chờ duyệt để người dùng thử duyệt và tính lại lương')
        self.stdout.write(self.style.SUCCESS('Created 8 DEMO employees. Periods: ' + ', '.join(f'{month:02}/{year}' for month in months)))
        self.stdout.write(f'Year: {year}. Empty-period example: 12/{year}.')
        if 11 in months:
            self.stdout.write('Attendance 11 is reopened for approval practice; approve attendance then recalculate payroll 11.')
        self.stdout.write('New demo accounts (same generated password): ' + ', '.join(usernames))
        if not reuse_users:
            self.stdout.write('DEMO PASSWORD: ' + password)
        self.stdout.write('Existing users and passwords were not changed. Demo users are NOT staff/superusers.')

    def leave(self, employee, day, units, paid):
        leave = LeaveDay(employee=employee, date=day, units=units, paid=paid,
                         reason='DEMO: nghỉ phép minh họa đã duyệt', approved=True)
        leave.full_clean()
        leave.save()
