import calendar
from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from bang_cong.models import AttendancePeriod, WorkCalendarDay


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
        if AttendancePeriod.objects.filter(year=year, month=month, status='approved').exists():
            raise CommandError('Kỳ đã duyệt, không được sửa lịch.')
        if WorkCalendarDay.objects.filter(date__year=year, date__month=month).exists():
            raise CommandError('Tháng đã có lịch. Chỉnh từng ngày trong quản trị; không ghi đè tự động.')
        rows = []
        for number in range(1, calendar.monthrange(year, month)[1] + 1):
            day = date(year, month, number)
            kind = 'holiday' if day in holidays else ('work' if day.weekday() in workdays else 'rest')
            rows.append(WorkCalendarDay(date=day, kind=kind, expected_units=Decimal(1 if kind == 'work' else 0)))
        WorkCalendarDay.objects.bulk_create(rows)
        self.stdout.write(self.style.SUCCESS(f'Created {len(rows)} calendar days. Review the calendar and confirm policy before approval.'))
