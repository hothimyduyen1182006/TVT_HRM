import re

from django import forms
from django.utils import timezone
from employees.access import visible_employees
from employees.filters import PeriodFilter
from employees.models import Employee
from .models import Bonus


class VNDField(forms.DecimalField):
    """Accept plain or thousands-grouped whole-VND values."""

    def to_python(self, value):
        if value in self.empty_values:
            return None

        raw_value = str(value).strip().replace('₫', '').replace('VNĐ', '').replace(' ', '')
        is_plain_number = re.fullmatch(r'\d+', raw_value)
        is_grouped_number = re.fullmatch(r'\d{1,3}(?:[.,]\d{3})+', raw_value)
        if not (is_plain_number or is_grouped_number):
            raise forms.ValidationError('Nhập số tiền VNĐ nguyên, ví dụ 500000 hoặc 500.000.')

        normalized_value = raw_value.replace('.', '').replace(',', '')
        if is_plain_number and 0 < int(normalized_value) < 10000:
            normalized_value += '000'
        return super().to_python(normalized_value)


class BonusFilter(PeriodFilter):
    q = forms.CharField(
        label='Từ khóa (Họ tên)',
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Tìm theo họ hoặc tên...'}),
    )
    status = forms.ChoiceField(label='Trạng thái', required=False, choices=[('', 'Tất cả'), *Bonus.STATUSES])

    def __init__(self, user, data=None):
        super().__init__(user, data)
        self.fields['department'].empty_label = 'Tất cả'
        self.fields['employee'].empty_label = 'Tất cả'
        self.fields['month'].widget = forms.Select(choices=[(m, f'Tháng {m:02}') for m in range(1, 13)])
        self.fields['year'].widget = forms.Select(choices=[(y, f'Năm {y}') for y in range(2000, timezone.localdate().year + 2)])


class PersonalBonusFilter(forms.Form):
    month = forms.IntegerField(label='Tháng', min_value=1, max_value=12, required=False)
    year = forms.IntegerField(label='Năm', min_value=2000, max_value=2100, required=False)
    status = forms.ChoiceField(label='Trạng thái', required=False,
                               choices=[('', 'Tất cả'), *Bonus.STATUSES])

    def __init__(self, data=None):
        today = timezone.localdate()
        initial = {'month': '', 'year': today.year}
        super().__init__(data=data if data else None, initial=initial)
        self.fields['month'].widget = forms.Select(choices=[('', 'Tất cả')] + [(m, f'Tháng {m:02}') for m in range(1, 13)])
        self.fields['year'].widget = forms.Select(choices=[(y, f'Năm {y}') for y in range(2000, today.year + 2)])


class BonusProposalForm(forms.Form):
    month = forms.IntegerField(label='Tháng', min_value=1, max_value=12)
    year = forms.IntegerField(label='Năm', min_value=2000, max_value=2100)
    employee = forms.ModelChoiceField(label='Nhân viên', queryset=Employee.objects.none())
    name = forms.CharField(label='Tên khoản thưởng khác', max_length=100, required=False)
    reason = forms.CharField(label='Lý do đề xuất', widget=forms.Textarea(attrs={'rows': 3}), required=False)
    amount = VNDField(
        label='Số tiền (VNĐ)',
        help_text='Nhập 500 để tính là 500.000 VNĐ, hoặc nhập đầy đủ 500000.',
        min_value=0,
        max_digits=12,
        decimal_places=0,
        required=False,
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].queryset = visible_employees(user).filter(is_active=True)
        self.fields['employee'].label_from_instance = lambda item: f'{item.code} · {item.full_name} · {item.department.name}'
        self.fields['employee'].empty_label = 'Chọn nhân viên'
        self.fields['name'].widget.attrs['placeholder'] = 'Ví dụ: Thưởng dự án'
        self.fields['reason'].widget.attrs.update({'rows': 4, 'placeholder': 'Nêu ngắn gọn căn cứ và thành tích được đề xuất thưởng.'})
        self.fields['amount'].widget = forms.TextInput(attrs={
            'placeholder': '500 hoặc 500.000',
            'inputmode': 'numeric',
            'autocomplete': 'off',
        })
        today = timezone.localdate()
        self.fields['month'].initial = today.month
        self.fields['year'].initial = today.year
        self.fields['month'].widget = forms.Select(choices=[(m, f'Tháng {m:02}') for m in range(1, 13)])
        self.fields['year'].widget = forms.Select(choices=[(y, f'Năm {y}') for y in range(2000, today.year + 2)])

    def clean(self):
        data = super().clean()
        data['name'] = (data.get('name') or '').strip()
        data['reason'] = (data.get('reason') or '').strip()
        fields = (data.get('name'), data.get('reason'), data.get('amount') is not None)
        if not all(fields):
            raise forms.ValidationError('Đề xuất thưởng khác cần có tên thưởng, lý do và số tiền.')
        return data
