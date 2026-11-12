import calendar
from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from bang_cong.models import KyCong, LichLamViec


class Command(BaseCommand):
    help = 'Tạo lịch theo ngày làm việc chỉ định; không ghi đè lịch đã có.'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, required=True)
        parser.add_argument('--month', type=int, required=True)
        parser.add_argument('--workdays', required=True, help='0=Thứ Hai ... 6=Chủ nhật; ví dụ 0,1,2,3,4')
        parser.add_argument('--holidays', default='', help='Ngày lễ, YYYY-MM-DD cách nhau bằng dấu phẩy')

    @transaction.atomic
    def handle(self, *args, **options):
        year, month = options['year'], options['month']
        try:
            if not 2000 <= year <= 2100 or not 1 <= month <= 12:
                raise ValueError
            workdays = {int(value.strip()) for value in options['workdays'].split(',')}
            holidays = {date.fromisoformat(value.strip()) for value in options['holidays'].split(',') if value.strip()}
            if not workdays or not workdays.issubset(set(range(7))):
                raise ValueError
            if any(day.year != year or day.month != month for day in holidays):
                raise ValueError
        except ValueError:
            raise CommandError('Tháng/năm, workdays hoặc holidays không hợp lệ.')
        if KyCong.objects.filter(nam=year, thang=month, trang_thai='approved').exists():
            raise CommandError('Kỳ đã duyệt, không được sửa lịch.')
        if LichLamViec.objects.filter(ngay__year=year, ngay__month=month).exists():
            raise CommandError('Tháng đã có lịch. Chỉnh từng ngày trong quản trị; không ghi đè tự động.')
        rows = []
        for number in range(1, calendar.monthrange(year, month)[1] + 1):
            day = date(year, month, number)
            kind = 'holiday' if day in holidays else ('work' if day.weekday() in workdays else 'rest')
            rows.append(LichLamViec(ngay=day, loai_ngay=kind, cong_chuan=Decimal(1 if kind == 'work' else 0)))
        LichLamViec.objects.bulk_create(rows)
        self.stdout.write(self.style.SUCCESS(f'Created {len(rows)} calendar days. Review the calendar and confirm policy before approval.'))
