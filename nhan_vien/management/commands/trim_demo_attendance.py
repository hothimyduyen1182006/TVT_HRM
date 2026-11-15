"""Loại bỏ công mẫu chưa diễn ra, không áp dụng cho nhân viên thật."""

from django.db.models import F
from datetime import date
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction, connection
from bang_cong.models import ChamCong, ChotBangCong
from bang_luong.models import PayrollPeriod as KyCong
from nghi_phep.models import NgayNghi
from bang_luong.models import PayrollPeriod, Luong, PayrollAuditLog


class Command(BaseCommand):
    help = 'Giữ công demo trước ngày chỉ định; gỡ kết quả lương demo bị ảnh hưởng.'

    def add_arguments(self, parser):
        parser.add_argument('--from-date', required=True, type=date.fromisoformat)

    @transaction.atomic
    def handle(self, *args, **options):
        cutoff = options['from_date']
        ma_cong_mau = []
        if 'attendance_chamcong_archive_0017' in connection.introspection.table_names():
            with connection.cursor() as cursor:
                cursor.execute('SELECT Ma_cham_cong FROM attendance_chamcong_archive_0017 WHERE ghi_chu LIKE %s', ['DEMO:%'])
                ma_cong_mau = [row[0] for row in cursor.fetchall()]
        records = ChamCong.objects.filter(nhan_vien__code__startswith='DEMO-',
            ngay__gte=cutoff, pk__in=ma_cong_mau)
        periods = list(KyCong.objects.select_for_update().filter(
            nam__gte=cutoff.year))
        periods = [p for p in periods if (p.nam, p.thang) >= (cutoff.year, cutoff.month)]
        if any(p.trang_thai == 'approved' or p.employee_approvals.exists() for p in periods):
            raise CommandError('Công đã duyệt không được xóa hoặc mở lại.')
        actor = get_user_model().objects.filter(username='demo_hr').first()
        if not actor:
            raise CommandError('Không tìm thấy tài khoản demo_hr.')
        payrolls = PayrollPeriod.objects.select_for_update().filter(pk__in=periods)
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
            approvals = ChotBangCong.objects.filter(tong_hop__ky_cong=period, tong_hop__nhan_vien__code__startswith='DEMO-')
            if approvals.exists():
                raise CommandError('Công đã duyệt không được xóa hoặc mở lại.')
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
        NgayNghi.objects.filter(
            don_nghi_phep__nhan_vien__code__startswith='DEMO-',
            don_nghi_phep__ly_do__startswith='DEMO:',
            ngay__gte=cutoff,
        ).delete()
        self.stdout.write(self.style.SUCCESS(f'Removed {count} demo attendance records from {cutoff}.'))




