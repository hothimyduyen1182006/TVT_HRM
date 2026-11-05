from collections import Counter
from decimal import Decimal
from django import forms
from django.db.models import Count
from django.utils import timezone
from employees.access import visible_employees
from employees.models import Department
from attendance.models import AttendanceRecord, AttendancePeriod
from leaves.models import LeaveDay


class DashboardFilter(forms.Form):
    date = forms.DateField(label='Ngày thống kê', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    department = forms.ModelChoiceField(label='Phòng ban', queryset=Department.objects.none(), required=False, empty_label='Tất cả phòng ban')

    def __init__(self, user, data=None):
        values = {'date': timezone.localdate().isoformat()}
        if data:
            values.update(data.dict())
        super().__init__(values)
        self.fields['department'].queryset = Department.objects.filter(pk__in=visible_employees(user).values('department_id')).order_by('name')


def dashboard_context(user, form):
    day = form.cleaned_data['date']
    employees = visible_employees(user).filter(is_active=True, hire_date__lte=day)
    period = AttendancePeriod.objects.filter(year=day.year, month=day.month).first()
    records = {r.employee_id: r for r in AttendanceRecord.objects.filter(employee__in=employees, date=day)}
    leaves = set(LeaveDay.objects.filter(employee__in=employees, date=day, approved=True).values_list('employee_id', flat=True))
    counts = {'ontime': 0, 'late': 0, 'unchecked': 0}
    rows = []
    for employee in employees.select_related('department', 'position').order_by('code'):
        record = records.get(employee.pk)
        if record and record.check_in:
            if period:
                state, label = ('late', 'Đi trễ') if record.check_in > period.start_time else ('ontime', 'Đúng giờ')
                counts[state] += 1
            else:
                state, label = 'recorded', 'Đã check-in · chưa có ca cấu hình'
        else:
            counts['unchecked'] += 1
            if employee.pk in leaves:
                state, label = 'leave', 'Nghỉ phép đã duyệt'
            elif record and record.status == 'absent':
                state, label = 'absent', 'Nghỉ không phép đã ghi nhận'
            else:
                state, label = 'unchecked', 'Chưa chấm công'
        rows.append({'employee': employee, 'state': state, 'label': label})
    departments = list(employees.values('department_id', 'department__name').annotate(total=Count('pk')).order_by('-total', 'department__name'))
    highest = max((item['total'] for item in departments), default=1)
    for item in departments:
        item['height'] = int(Decimal(item['total']) / highest * 100)
    genders = Counter(employees.values_list('gender', flat=True))
    total = employees.count()
    gender_rows, cumulative = [], Decimal(0)
    for value, label, color in [('Nam', 'Nam', '#14385e'), ('Nữ', 'Nữ', '#287af0'), ('', 'Chưa cập nhật', '#cbd5e1')]:
        count = genders.get(value, 0) if value else total - genders.get('Nam', 0) - genders.get('Nữ', 0)
        percent = Decimal(count) / total * 100 if total else Decimal(0)
        cumulative += percent
        gender_rows.append({'label': label, 'value': value or 'unknown', 'count': count, 'percent': round(percent), 'color': color, 'end': format(cumulative, '.4f')})
    selected = form.cleaned_data['department']
    if selected:
        rows = [r for r in rows if r['employee'].department_id == selected.pk]
    return {'selected_day': day, 'total_employees': total, 'department_count': len(departments), 'departments': departments,
            'genders': gender_rows, 'attendance_counts': counts, 'employee_rows': rows, 'schedule_missing': period is None}
