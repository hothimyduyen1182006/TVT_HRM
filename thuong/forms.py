import re

from django import forms
from django.utils import timezone

from nhan_vien.access import nhan_vien_duoc_hien_thi
from nhan_vien.filters import BoLocKy
from nhan_vien.models import NhanVien

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
            raise forms.ValidationError('Nhập đầy đủ số tiền, ví dụ 500000 VNĐ.')

        normalized_value = raw_value.replace('.', '').replace(',', '')
        return super().to_python(normalized_value)


class BonusFilter(BoLocKy):
    q = forms.CharField(
        label='Từ khóa (Họ tên)',
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Tìm theo họ hoặc tên...'}),
    )
    status = forms.ChoiceField(
        label='Trạng thái', required=False, choices=[('', 'Tất cả'), *Bonus.STATUSES]
    )

    def __init__(self, user, data=None, default_current_period=False):
        super().__init__(user, data)
        self.fields['thang'].required = False
        self.fields['nam'].required = False
        self.fields['phong_ban'].empty_label = 'Tất cả'
        self.fields['nhan_vien'].empty_label = 'Tất cả'
        self.fields['thang'].widget = forms.Select(choices=[('', 'Tất cả')] + [
            (m, f'Tháng {m:02}') for m in range(1, 13)
        ])
        self.fields['nam'].widget = forms.Select(choices=[('', 'Tất cả')] + [
            (y, f'Năm {y}') for y in range(2000, timezone.localdate().year + 2)
        ])
        if not default_current_period:
            if not data or not ('thang' in data or 'month' in data):
                self.data['thang'] = ''
            if not data or not ('nam' in data or 'year' in data):
                self.data['nam'] = ''


class PersonalBonusFilter(forms.Form):
    month = forms.IntegerField(label='Tháng', min_value=1, max_value=12, required=False)
    year = forms.IntegerField(label='Năm', min_value=2000, max_value=2100, required=False)
    status = forms.ChoiceField(label='Trạng thái', required=False,
                               choices=[('', 'Tất cả'), *Bonus.STATUSES])

    def __init__(self, data=None):
        today = timezone.localdate()
        if data is None:
            super().__init__(initial={'month': today.month, 'year': today.year})
        else:
            mutable_data = data.copy()
            mutable_data.setdefault('month', today.month)
            mutable_data.setdefault('year', today.year)
            super().__init__(data=mutable_data)
        self.fields['month'].widget = forms.Select(choices=[('', 'Tất cả')] + [
            (month, f'Tháng {month:02}') for month in range(1, 13)
        ])
        self.fields['year'].widget = forms.Select(choices=[('', 'Tất cả')] + [
            (year, f'Năm {year}') for year in range(2000, today.year + 2)
        ])


class BonusProposalForm(forms.Form):
    month = forms.IntegerField(label='Tháng', min_value=1, max_value=12)
    year = forms.IntegerField(label='Năm', min_value=2000, max_value=2100)
    employee = forms.ModelChoiceField(label='Nhân viên', queryset=NhanVien.objects.none())
    name = forms.CharField(label='Tên khoản thưởng khác', max_length=100, required=False)
    reason = forms.CharField(label='Lý do đề xuất', widget=forms.Textarea(attrs={'rows': 3}), required=False)
    amount = VNDField(
        label='Số tiền (VNĐ)',
        min_value=0,
        max_digits=12,
        decimal_places=0,
        required=False,
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].queryset = nhan_vien_duoc_hien_thi(user).filter(dang_hoat_dong=True)
        self.fields['employee'].label_from_instance = (
            lambda item: f'{item.ma_ho_so} · {item.ho_va_ten} · {item.phong_ban.ten_phong_ban}'
        )
        self.fields['employee'].empty_label = 'Chọn nhân viên'
        self.fields['name'].widget.attrs['placeholder'] = 'Ví dụ: Thưởng dự án'
        self.fields['reason'].widget.attrs.update({
            'rows': 4,
            'placeholder': 'Nêu ngắn gọn căn cứ và thành tích được đề xuất thưởng.',
        })
        self.fields['amount'].widget = forms.TextInput(attrs={
            'placeholder': 'Ví dụ: 500000',
            'inputmode': 'numeric',
            'autocomplete': 'off',
        })
        today = timezone.localdate()
        self.fields['month'].widget = forms.Select(choices=[('', 'Chọn tháng')] + [
            (m, f'Tháng {m:02}') for m in range(1, 13)
        ])
        self.fields['year'].widget = forms.Select(choices=[('', 'Chọn năm')] + [
            (y, f'Năm {y}') for y in range(2000, today.year + 2)
        ])

    def clean(self):
        data = super().clean()
        data['name'] = (data.get('name') or '').strip()
        data['reason'] = (data.get('reason') or '').strip()
        fields = (data.get('name'), data.get('reason'), data.get('amount') is not None)
        if not all(fields):
            raise forms.ValidationError('Đề xuất thưởng khác cần có tên thưởng, lý do và số tiền.')
        return data
