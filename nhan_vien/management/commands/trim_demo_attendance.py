"""Loại bỏ công mẫu chưa diễn ra, không áp dụng cho nhân viên thật."""

from django.db.models import F
from datetime import date
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from bang_cong.models import KyCong, ChamCong, ChotBangCong, NhatKyCong
from nghi_phep.models import LeaveDay
from bang_luong.models import PayrollPeriod, Luong, PayrollAuditLog


class Command(BaseCommand):
    help = 'Giữ công demo trước ngày chỉ định; gỡ kết quả lương demo bị ảnh hưởng.'

    def add_arguments(self, parser):
        parser.add_argument('--from-date', required=True, type=date.fromisoformat)

    @transaction.atomic
    def handle(self, *args, **options):
        cutoff = options['from_date']
        records = ChamCong.objects.filter(nhan_vien__code__startswith='DEMO-',
            ngay__gte=cutoff, ghi_chu__startswith='DEMO:')
        periods = list(KyCong.objects.select_for_update().filter(
            nam__gte=cutoff.year))
        periods = [p for p in periods if (p.nam, p.thang) >= (cutoff.year, cutoff.month)]
        actor = get_user_model().objects.filter(username='demo_hr').first()
        if not actor:
            raise CommandError('Không tìm thấy tài khoản demo_hr.')
        payrolls = PayrollPeriod.objects.select_for_update().filter(attendance_period__in=periods)
        salary = Luong.objects.filter(ky_luong__in=payrolls, nhan_vien__code__startswith='DEMO-')
        if salary.filter(trang_thai='paid').exists():
            raise CommandError('Có lương đã chi trả; không tự sửa dữ liệu này.')
        for payroll in payrolls:
            rows = salary.filter(ky_luong=payroll)
            if rows.exists():
                PayrollAuditLog.objects.create(period=payroll, actor=actor, action='trim_demo',
                    reason=f'Gỡ kết quả demo cả tháng: chỉ giữ công trước {cutoff}',
                    snapshot={'records': list(rows.values('id', **{'employee_id': F('nhan_vien_id'), 'status': F('trang_thai'), 'breakdown': F('chi_tiet')}))})
                rows.delete()
            if not payroll.records.exists():
                payroll.status = 'pending'
                payroll.approved_by = None
                payroll.approved_at = None
                payroll.attendance_revision = 0
                payroll.save()
        for period in periods:
            approvals = ChotBangCong.objects.filter(ky_cong=period, nhan_vien__code__startswith='DEMO-')
            if approvals.exists():
                NhatKyCong.objects.create(nguoi_thuc_hien=actor, hanh_dong='trim_demo',
                    ly_do=f'Gỡ duyệt công demo cả tháng sau khi xóa công từ {cutoff}',
                    du_lieu_cu={'employee_ids': list(approvals.values_list('nhan_vien_id', flat=True))},
                    du_lieu_moi={'period': period.pk, 'status': 'pending'})
                approvals.delete()
            if period.trang_thai == 'approved' and not period.employee_approvals.exists():
                period.trang_thai = 'pending'
                period.nguoi_duyet = None
                period.ngay_duyet = None
                period.ds_nhan_vien = []
            period.phien_ban += 1
            period.save()
        count = records.count()
        records.delete()
        # Các khoản nghỉ/OT tạo bởi bộ demo cho ngày tương lai cũng cần gỡ.
        LeaveDay.objects.filter(employee__code__startswith='DEMO-', date__gte=cutoff,
                                reason__startswith='DEMO:').delete()
        self.stdout.write(self.style.SUCCESS(f'Removed {count} demo attendance records from {cutoff}.'))
