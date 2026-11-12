"""Dữ liệu hiển thị; không thay đổi công thức hoặc tạo bản ghi chấm công."""
import calendar
from datetime import date
from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import Sum, Count, Q, F, Exists, OuterRef

from bang_cong.models import ChamCong, LichLamViec, NhatKyCong
from bang_cong.models import ChotBangCong, KyCong
from bang_cong.forms import AUDIT_FIELDS, AttendanceFilter, DailyFilter, HistoryFilter
from nhan_vien.models import Employee
from .calculations import automatic_overtime

ZERO = Decimal(0)


def overtime_context(record):
    return {'automatic_ot': automatic_overtime(record)}


def month_summary(employees, year, month, period):
    scope = employees.values('pk')
    records = ChamCong.objects.filter(nhan_vien_id__in=scope, ngay__year=year, ngay__month=month)
    grouped = records.values(**{'employee_id': F('nhan_vien_id')}).annotate(paid=Sum('tong_cong'), actual=Sum('cong_thuc_te'),
        leave=Sum('cong_nghi_co_luong'), hours=Sum('so_gio_lam'), late=Sum('so_phut_tre'),
        late_count=Count('pk', filter=Q(so_phut_tre__gt=0)),
        incomplete=Count('pk', filter=Q(trang_thai='incomplete')), absent=Count('pk', filter=Q(trang_thai='absent')))
    by_employee = {row['employee_id']: row for row in grouped}
    days = {d.ngay: d for d in LichLamViec.objects.filter(ngay__year=year, ngay__month=month)}
    ot_totals = {}
    for record in records.select_related('nhan_vien'):
        ot_totals[record.nhan_vien_id] = ot_totals.get(record.nhan_vien_id, ZERO) + automatic_overtime(record, period, days.get(record.ngay))['hours']
    standard = LichLamViec.objects.filter(ngay__year=year, ngay__month=month).aggregate(value=Sum('cong_chuan'))['value']
    result = []
    approval_updates = ChamCong.objects.filter(nhan_vien_id=OuterRef('nhan_vien_id'),
        ngay__year=year, ngay__month=month, ngay_cap_nhat__gt=OuterRef('ngay_duyet'))
    approved_ids = set(ChotBangCong.objects.filter(ky_cong=period).annotate(
        changed_after_approval=Exists(approval_updates)).filter(changed_after_approval=False
        ).values_list('nhan_vien_id', flat=True)) if period else set()
    for employee in employees:
        values = by_employee.get(employee.pk, {})
        state = 'empty' if not values else ('approved' if employee.pk in approved_ids or (period and period.trang_thai == 'approved')
                else ('incomplete' if values['incomplete'] else 'pending'))
        result.append({'employee': employee, 'standard': standard, 'paid': values.get('paid', ZERO),
            'actual': values.get('actual', ZERO), 'leave': values.get('leave', ZERO),
            'hours': values.get('hours', ZERO), 'late': values.get('late', 0), 'late_count': values.get('late_count', 0),
            'absent': values.get('absent', 0), 'ot': ot_totals.get(employee.pk,ZERO), 'state': state,
            'state_label': {'empty': 'Chưa có dữ liệu', 'approved': 'Đã duyệt', 'pending': 'Chờ duyệt',
                            'incomplete': 'Cần kiểm tra'}[state], 'has_records': bool(values)})
    return result


def daily_rows(employee, year, month):
    records = {r.ngay: r for r in ChamCong.objects.filter(nhan_vien=employee, ngay__year=year, ngay__month=month).select_related('nhan_vien')}
    calendar_days = {r.ngay: r for r in LichLamViec.objects.filter(ngay__year=year, ngay__month=month)}
    period = KyCong.objects.filter(nam=year, thang=month).first()
    overtime = {r.ngay: automatic_overtime(r, period, calendar_days.get(r.ngay)) for r in records.values()}
    result = []
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        value = date(year, month, day)
        if value < employee.hire_date:
            continue
        record, schedule = records.get(value), calendar_days.get(value)
        state, label = 'incomplete', 'Chưa có dữ liệu'
        if record:
            if record.trang_thai == 'present':
                state, label = ('late', 'Đi làm trễ') if record.so_phut_tre else ('present', 'Đi đúng giờ')
            elif record.trang_thai == 'leave':
                state, label = 'leave', 'Nghỉ có lương' if record.cong_nghi_co_luong else 'Nghỉ không lương'
            elif record.trang_thai == 'absent':
                state, label = 'absent', 'Nghỉ không phép'
            else:
                label = 'Thiếu dữ liệu'
        elif schedule and schedule.loai_ngay != 'work':
            state = 'rest'
            label = schedule.ghi_chu or ('Nghỉ lễ' if schedule.loai_ngay == 'holiday' else 'Nghỉ hằng tuần')
        result.append({'date': value, 'weekday': ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'][value.weekday()],
            'record': record, 'state': state, 'label': label, 'ot': overtime.get(value, {}).get('hours', ZERO),
            'ot_error': overtime.get(value, {}).get('error', ''),
            'ot_warnings': overtime.get(value, {}).get('warnings', [])})
    return result


def history_logs(employee, year, month):
    # save_record là tên sự kiện cũ: chỉ giữ lần sửa có cả trước/sau, không lấy lần tạo.
    return NhatKyCong.objects.filter(hanh_dong__in=['edit_record', 'save_record'],
        du_lieu_moi__employee_id=str(employee.pk), du_lieu_moi__date__startswith=f'{year:04}-{month:02}-'
        ).exclude(du_lieu_cu={}).exclude(du_lieu_cu=F('du_lieu_moi')).select_related('nguoi_thuc_hien').prefetch_related('adjustments').order_by('-ngay_tao', '-pk')


def history_rows(logs, field=''):
    result = []
    labels = dict(ChamCong._meta.get_field('trang_thai').choices)
    labels.update({'pending': 'Chờ duyệt', 'approved': 'Đã duyệt'})
    for log in logs:
        if log.hanh_dong not in ['edit_record', 'save_record'] or not log.du_lieu_cu or log.du_lieu_cu == log.du_lieu_moi:
            continue
        changes = {item.truong_dieu_chinh: (item.gia_tri_cu, item.gia_tri_moi) for item in log.adjustments.all()}
        for key, title in AUDIT_FIELDS.items():
            old, new = changes.get(key, (log.du_lieu_cu.get(key, ''), log.du_lieu_moi.get(key, '')))
            if old == new or (field and field != key):
                continue
            result.append({'time': log.ngay_tao, 'date': log.du_lieu_moi.get('date'), 'field': title,
                'old': labels.get(old, old) if key in ['status', 'approval_status'] else old,
                'new': labels.get(new, new) if key in ['status', 'approval_status'] else new,
                'actor': log.nguoi_thuc_hien.get_full_name() or log.nguoi_thuc_hien.username, 'reason': log.ly_do})
    return result


def month_data(request, employee):
    """Tổng hợp ngày công và bộ lọc cho một nhân viên, không thay đổi dữ liệu."""
    form = DailyFilter(request.user, request.GET)
    rows, summary, period, progress, average = [], None, None, 0, '—'
    month_query = ''
    if form.is_valid():
        data = form.cleaned_data
        month_query = urlencode({'month': data['month'], 'year': data['year']})
        period = KyCong.objects.filter(nam=data['year'], thang=data['month']).first()
        summary = month_summary(Employee.objects.filter(pk=employee.pk), data['year'], data['month'], period)[0]
        rows = daily_rows(employee, data['year'], data['month'])
        work_count = sum(1 for row in rows if row['record'] and row['record'].gio_vao)
        if work_count:
            minutes = int(summary['hours'] * 60 / work_count)
            average = f'{minutes // 60}:{minutes % 60:02}'
        if summary['standard']:
            progress = max(0, min(100, int(summary['paid'] / summary['standard'] * 100)))
        if data['start']:
            rows = [r for r in rows if r['date'] >= data['start']]
        if data['end']:
            rows = [r for r in rows if r['date'] <= data['end']]
        if data['state']:
            state = data['state']
            unit_fields = {'paid': 'tong_cong', 'actual': 'cong_thuc_te', 'paid_leave': 'cong_nghi_co_luong'}
            if state in unit_fields:
                rows = [r for r in rows if r['record'] and getattr(r['record'], unit_fields[state]) > 0]
            elif state == 'ot':
                rows = [r for r in rows if r['ot'] > 0]
            else:
                rows = [r for r in rows if r['state'] == state]
    stat_params = request.GET.copy()
    stat_params.pop('page', None)
    stat_params.pop('state', None)
    if form.is_valid():
        stat_params['month'] = form.cleaned_data['month']
        stat_params['year'] = form.cleaned_data['year']
    return {'form': form, 'rows': rows, 'summary': summary, 'period': period, 'progress': progress,
            'average': average, 'month_query': month_query, 'stat_query': stat_params.urlencode()}


def audit_data(request, employee):
    """Lọc lịch sử theo kỳ công và điều kiện người dùng đã chọn."""
    period_form = AttendanceFilter(request.user, request.GET)
    logs = NhatKyCong.objects.none()
    month_query = ''
    if period_form.is_valid():
        data = period_form.cleaned_data
        month_query = urlencode({'month': data['month'], 'year': data['year']})
        logs = history_logs(employee, data['year'], data['month'])
    form = HistoryFilter(request.GET, logs)
    rows = []
    if form.is_valid() and period_form.is_valid():
        data = form.cleaned_data
        if data['start']:
            logs = logs.filter(ngay_tao__date__gte=data['start'])
        if data['end']:
            logs = logs.filter(ngay_tao__date__lte=data['end'])
        if data['actor']:
            logs = logs.filter(nguoi_thuc_hien=data['actor'])
        rows = history_rows(logs, data['field'])
    return {'form': form, 'period_form': period_form, 'rows': rows, 'month_query': month_query}
