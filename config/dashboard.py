from collections import Counter
from decimal import Decimal
from django import forms
from django.db.models import Count, F
from django.utils import timezone
from nhan_vien.access import nhan_vien_duoc_hien_thi
from nhan_vien.models import PhongBan
from bang_cong.models import ChamCong
from bang_cong.services.cham_cong_service import GIO_BAT_DAU
from nghi_phep.models import NgayNghi


class DashboardFilter(forms.Form):
    date = forms.DateField(label='Ngày thống kê', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    department = forms.ModelChoiceField(label='Phòng ban', queryset=PhongBan.objects.none(), required=False, empty_label='Tất cả phòng ban')

    def __init__(self, user, data=None):
        values = {'date': timezone.localdate().isoformat()}
        if data:
            values.update(data.dict())
        super().__init__(values)
        self.fields['department'].queryset = PhongBan.objects.filter(pk__in=nhan_vien_duoc_hien_thi(user).values('phong_ban_id')).order_by('ten_phong_ban')


def loc_nhan_vien_theo_cham_cong(employees, ngay, trang_thai):
    """Lọc danh sách mở từ thống kê chấm công ngày trên Dashboard."""
    employees = employees.filter(dang_hoat_dong=True, ngay_vao_lam__lte=ngay)
    attendance = ChamCong.objects.filter(ngay=ngay, gio_vao__isnull=False)
    if trang_thai == 'unchecked':
        return employees.exclude(pk__in=attendance.values('nhan_vien_id'))
    if trang_thai == 'ontime':
        attendance = attendance.filter(gio_vao__lte=GIO_BAT_DAU)
    elif trang_thai == 'late':
        attendance = attendance.filter(gio_vao__gt=GIO_BAT_DAU)
    else:
        return employees
    return employees.filter(pk__in=attendance.values('nhan_vien_id'))


def dashboard_context(user, form):
    day = form.cleaned_data['date']
    all_employees = nhan_vien_duoc_hien_thi(user)
    employees = all_employees.filter(dang_hoat_dong=True, ngay_vao_lam__lte=day)
    records = {r.nhan_vien_id: r for r in ChamCong.objects.filter(nhan_vien__in=employees, ngay=day)}
    leaves = set(NgayNghi.objects.filter(
        don_nghi_phep__nhan_vien__in=employees,
        don_nghi_phep__trang_thai='da_duyet',
        ngay=day,
    ).values_list('don_nghi_phep__nhan_vien_id', flat=True))
    counts = {'ontime': 0, 'late': 0, 'unchecked': 0}
    rows = []
    for employee in employees.select_related('phong_ban', 'chuc_vu').order_by('ma_ho_so'):
        record = records.get(employee.pk)
        if record and record.gio_vao:
            state, label = ('late', 'Đi trễ') if record.gio_vao > GIO_BAT_DAU else ('ontime', 'Đúng giờ')
            counts[state] += 1
        else:
            counts['unchecked'] += 1
            if employee.pk in leaves:
                state, label = 'leave', 'Nghỉ phép đã duyệt'
            elif record and record.trang_thai == 'absent':
                state, label = 'absent', 'Nghỉ không phép đã ghi nhận'
            else:
                state, label = 'unchecked', 'Chưa chấm công'
        rows.append({'employee': employee, 'state': state, 'label': label})
    departments = list(all_employees.values('phong_ban_id', ten_phong_ban=F('phong_ban__ten_phong_ban')).annotate(total=Count('pk')).order_by('-total', 'ten_phong_ban'))
    highest = max((item['total'] for item in departments), default=1)
    for item in departments:
        item['height'] = int(Decimal(item['total']) / highest * 100)
    genders = Counter(all_employees.values_list('gioi_tinh', flat=True))
    total = all_employees.count()
    gender_rows, cumulative = [], Decimal(0)
    for value, label, color in [('Nam', 'Nam', '#14385e'), ('Nữ', 'Nữ', '#287af0'), ('', 'Chưa cập nhật', '#cbd5e1')]:
        count = genders.get(value, 0) if value else total - genders.get('Nam', 0) - genders.get('Nữ', 0)
        percent = Decimal(count) / total * 100 if total else Decimal(0)
        cumulative += percent
        gender_rows.append({'label': label, 'value': value or 'unknown', 'count': count, 'percent': round(percent), 'color': color, 'end': format(cumulative, '.4f')})
    selected = form.cleaned_data['department']
    if selected:
        rows = [r for r in rows if r['employee'].phong_ban_id == selected.pk]
    return {'selected_day': day, 'total_employees': total, 'department_count': len(departments), 'departments': departments,
            'genders': gender_rows, 'attendance_counts': counts, 'employee_rows': rows}
