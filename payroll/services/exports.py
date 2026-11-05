import csv
import io
import json
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from employees.access import require_role, HR, DIRECTOR
from payroll.models import PayrollExportLog, PayrollPeriod

FIELDS = ['employee_code', 'employee_name', 'department_name', 'base_salary', 'standard_units',
          'leave_units', 'paid_units', 'attendance_pay', 'ot_hours', 'ot_pay', 'bonus_pay', 'late_minutes',
          'allowance', 'insurance', 'tax', 'deductions', 'net_pay']


def safe_cell(value):
    # Không để tên/ghi chú do người dùng nhập trở thành công thức khi mở CSV.
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value


@transaction.atomic
def export_records(actor, queryset, fmt, month, year, scope):
    require_role(actor, HR, DIRECTOR)
    if fmt not in ['csv', 'json', 'txt']:
        raise ValidationError('Định dạng không hợp lệ.')
    period_ids = list(queryset.values_list('period_id', flat=True).distinct())
    # Giữ khóa trạng thái đến khi tạo nội dung và log, tránh xuất cùng lúc mở lại kỳ.
    list(PayrollPeriod.objects.select_for_update().filter(pk__in=period_ids).order_by('pk'))
    rows = list(queryset.select_related('period').order_by('employee_code'))
    if not rows:
        raise ValidationError('Không có dữ liệu để xuất.')
    if any(row.status not in ['approved', 'paid'] for row in rows):
        raise ValidationError('Không xuất bảng lương chưa duyệt.')
    data = [{**{name: str(getattr(row, name)) for name in FIELDS},
             'status': row.get_status_display(), 'breakdown': row.breakdown} for row in rows]
    if fmt == 'json':
        content = json.dumps(data, ensure_ascii=False, indent=2)
        content_type = 'application/json; charset=utf-8'
    else:
        output = io.StringIO(newline='')
        writer = csv.writer(output, delimiter=',' if fmt == 'csv' else '\t')
        writer.writerow(FIELDS + ['status'])
        for row in data:
            writer.writerow([safe_cell(row[key]) for key in FIELDS + ['status']])
        content = ('\ufeff' if fmt == 'csv' else '') + output.getvalue()
        content_type = 'text/csv; charset=utf-8' if fmt == 'csv' else 'text/plain; charset=utf-8'
    PayrollExportLog.objects.create(actor=actor, month=month, year=year, format=fmt,
                                    scope={**scope, 'record_ids': [row.pk for row in rows]})
    response = HttpResponse(content, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="payroll-{year}-{month:02}.{fmt}"'
    return response
