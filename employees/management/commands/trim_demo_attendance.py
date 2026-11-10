"""Loại bỏ công mẫu chưa diễn ra, không áp dụng cho nhân viên thật."""
from datetime import date
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from attendance.models import AttendancePeriod, AttendanceRecord, EmployeeAttendanceApproval, AttendanceAuditLog
from leaves.models import LeaveDay
from payroll.models import PayrollPeriod, PayrollRecord, PayrollAuditLog


class Command(BaseCommand):
    help = 'Giữ công demo trước ngày chỉ định; gỡ kết quả lương demo bị ảnh hưởng.'

    def add_arguments(self, parser):
        parser.add_argument('--from-date', required=True, type=date.fromisoformat)

    @transaction.atomic
    def handle(self, *args, **options):
        cutoff = options['from_date']
        records = AttendanceRecord.objects.filter(employee__code__startswith='DEMO-',
            date__gte=cutoff, note__startswith='DEMO:')
        periods = list(AttendancePeriod.objects.select_for_update().filter(
            year__gte=cutoff.year))
        periods = [p for p in periods if (p.year, p.month) >= (cutoff.year, cutoff.month)]
        actor = get_user_model().objects.filter(username='demo_hr').first()
        if not actor:
            raise CommandError('Không tìm thấy tài khoản demo_hr.')
        payrolls = PayrollPeriod.objects.select_for_update().filter(attendance_period__in=periods)
        salary = PayrollRecord.objects.filter(period__in=payrolls, employee__code__startswith='DEMO-')
        if salary.filter(status='paid').exists():
            raise CommandError('Có lương đã chi trả; không tự sửa dữ liệu này.')
        for payroll in payrolls:
            rows = salary.filter(period=payroll)
            if rows.exists():
                PayrollAuditLog.objects.create(period=payroll, actor=actor, action='trim_demo',
                    reason=f'Gỡ kết quả demo cả tháng: chỉ giữ công trước {cutoff}',
                    snapshot={'records': list(rows.values('id', 'employee_id', 'status', 'breakdown'))})
                rows.delete()
            if not payroll.records.exists():
                payroll.status = 'pending'
                payroll.approved_by = None
                payroll.approved_at = None
                payroll.attendance_revision = 0
                payroll.save()
        for period in periods:
            approvals = EmployeeAttendanceApproval.objects.filter(period=period, employee__code__startswith='DEMO-')
            if approvals.exists():
                AttendanceAuditLog.objects.create(actor=actor, action='trim_demo',
                    reason=f'Gỡ duyệt công demo cả tháng sau khi xóa công từ {cutoff}',
                    before={'employee_ids': list(approvals.values_list('employee_id', flat=True))},
                    after={'period': period.pk, 'status': 'pending'})
                approvals.delete()
            if period.status == 'approved' and not period.employee_approvals.exists():
                period.status = 'pending'
                period.approved_by = None
                period.approved_at = None
                period.employee_ids = []
            period.revision += 1
            period.save()
        count = records.count()
        records.delete()
        # Các khoản nghỉ/OT tạo bởi bộ demo cho ngày tương lai cũng cần gỡ.
        LeaveDay.objects.filter(employee__code__startswith='DEMO-', date__gte=cutoff,
                                reason__startswith='DEMO:').delete()
        self.stdout.write(self.style.SUCCESS(f'Removed {count} demo attendance records from {cutoff}.'))
