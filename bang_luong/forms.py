from django import forms
from .models import PayrollPeriod
from nhan_vien.filters import PeriodFilter
from django.utils import timezone


class BoLocBangLuong(PeriodFilter):
    q = forms.CharField(label='Từ khóa (Họ tên / ID)', required=False, max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Tìm theo họ tên hoặc ID...'}))
    status = forms.ChoiceField(label='Trạng thái', required=False,
        choices=[('', 'Tất cả'), *PayrollPeriod._meta.get_field('status').choices])

    def __init__(self, user, data=None):
        super().__init__(user, data)
        self.fields['department'].empty_label = 'Tất cả'
        thiet_lap_bo_chon_ky(self)


def thiet_lap_bo_chon_ky(form):
    form.fields['month'].widget = forms.Select(choices=[(month, f'Tháng {month:02}') for month in range(1, 13)])
    form.fields['year'].widget = forms.Select(choices=[(year, f'Năm {year}') for year in range(2000, 2101)])


class BoLocPhieuLuong(forms.Form):
    month = forms.IntegerField(label='Tháng', min_value=1, max_value=12)
    year = forms.IntegerField(label='Năm', min_value=2000, max_value=2100)

    def __init__(self, data=None):
        hom_nay = timezone.localdate()
        cac_gia_tri = {'month': hom_nay.month, 'year': hom_nay.year}
        if data:
            cac_gia_tri.update(data.dict() if hasattr(data, 'dict') else data)
        super().__init__(cac_gia_tri)
        thiet_lap_bo_chon_ky(self)

    def clean(self):
        data = super().clean()
        # Phiếu cá nhân không nhận bộ lọc có thể mở rộng sang người khác.
        if any(self.data.get(khoa) for khoa in ['employee', 'department', 'q', 'status']):
            raise forms.ValidationError('Phiếu cá nhân chỉ cho phép chọn tháng và năm.')
        return data
