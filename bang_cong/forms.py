from django import forms
from nhan_vien.access import visible_employees
from .models import AttendanceRecord
from nhan_vien.filters import PeriodFilter
from django.contrib.auth import get_user_model


class AttendanceFilter(PeriodFilter):
    day = forms.DateField(label='Ngày chấm công', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    day_state = forms.ChoiceField(label='Chấm công trong ngày', required=False,
        choices=[('', 'Tất cả'), ('ontime', 'Đúng giờ'), ('late', 'Đi trễ'), ('unchecked', 'Chưa check-in')])
    q = forms.CharField(label='Từ khóa (Họ tên)', required=False, max_length=150,
                        widget=forms.TextInput(attrs={'placeholder': 'Tìm theo họ hoặc tên...'}))
    review = forms.ChoiceField(label='Trạng thái', required=False, choices=[('', 'Tất cả'),
        ('approved', 'Đã duyệt'), ('pending', 'Chờ duyệt'), ('incomplete', 'Cần kiểm tra'), ('empty', 'Chưa có dữ liệu')])

    def __init__(self, user, data=None):
        super().__init__(user, data)
        self.fields['month'].widget = forms.Select(choices=[(n, f'Tháng {n:02}') for n in range(1, 13)])
        self.fields['year'].widget = forms.Select(choices=[(n, f'Năm {n}') for n in range(2000, 2101)])
        self.fields['department'].empty_label = 'Tất cả'

    def clean(self):
        data = super().clean()
        if data.get('day_state') and not data.get('day'):
            raise forms.ValidationError('Cần chọn ngày chấm công.')
        if data.get('day') and (data['day'].month != data.get('month') or data['day'].year != data.get('year')):
            raise forms.ValidationError('Ngày chấm công phải thuộc tháng/năm đã chọn.')
        return data


class DailyFilter(AttendanceFilter):
    state = forms.ChoiceField(label='Tình trạng', required=False, choices=[('', 'Tất cả'),
        ('paid', 'Có công hưởng lương'), ('actual', 'Có công thực tế'), ('paid_leave', 'Nghỉ hưởng lương'),
        ('late', 'Đi trễ'), ('leave', 'Nghỉ phép'), ('absent', 'Nghỉ không phép'),
        ('incomplete', 'Thiếu dữ liệu'), ('ot', 'Có tăng ca')])
    start = forms.DateField(label='Ngày bắt đầu', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    end = forms.DateField(label='Ngày kết thúc', required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    def clean(self):
        data = super().clean()
        if data.get('start') and data.get('end') and data['start'] > data['end']:
            raise forms.ValidationError('Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.')
        return data


AUDIT_FIELDS = {'overtime_hours': 'Giờ OT tự động', 'check_in': 'Giờ vào ca', 'check_out': 'Giờ ra ca', 'status': 'Tình trạng',
    'work_hours': 'Tổng giờ làm', 'late_minutes': 'Đi trễ (phút)', 'actual_units': 'Công thực tế',
    'paid_leave_units': 'Nghỉ hưởng lương', 'paid_units': 'Công hưởng lương', 'note': 'Ghi chú'}


class HistoryFilter(forms.Form):
    start = forms.DateField(label='Từ ngày điều chỉnh', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    end = forms.DateField(label='Đến ngày điều chỉnh', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    field = forms.ChoiceField(label='Trường điều chỉnh', choices=[('', 'Tất cả'), *AUDIT_FIELDS.items()], required=False)
    actor = forms.ModelChoiceField(label='Người điều chỉnh', queryset=get_user_model().objects.none(), required=False,
                                  empty_label='Tất cả')

    def __init__(self, data, logs):
        super().__init__(data)
        self.fields['actor'].queryset = get_user_model().objects.filter(pk__in=logs.values('actor_id')).order_by('username')

    def clean(self):
        data = super().clean()
        if data.get('start') and data.get('end') and data['start'] > data['end']:
            raise forms.ValidationError('Khoảng ngày điều chỉnh không hợp lệ.')
        return data


class AttendanceForm(forms.ModelForm):
    reason = forms.CharField(label='Lý do tạo/chỉnh sửa', widget=forms.Textarea)

    class Meta:
        model = AttendanceRecord
        fields = ['employee', 'date', 'check_in', 'check_out', 'status', 'note']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'check_in': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
                   'check_out': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M')}

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].queryset = visible_employees(user)
        if self.instance.pk:
            self.fields['employee'].disabled = True
            self.fields['date'].disabled = True
