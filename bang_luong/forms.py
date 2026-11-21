from django import forms
from django.utils import timezone

from nhan_vien.models import PhongBan

from .models import Luong


class BoLocBangLuong(forms.Form):
    thang = forms.IntegerField(min_value=1, max_value=12, label='Tháng')
    nam = forms.IntegerField(min_value=2000, max_value=2100, label='Năm')
    tu_khoa = forms.CharField(required=False, max_length=150, label='Nhân viên')
    phong_ban = forms.ModelChoiceField(
        queryset=PhongBan.objects.all(), required=False, label='Phòng ban',
    )
    trang_thai = forms.ChoiceField(required=False, label='Trạng thái', choices=[
        ('', 'Tất cả'),
        *Luong._meta.get_field('trang_thai').choices,
    ])

    def __init__(self, *args, **kwargs):
        data = args[0] if args else kwargs.get('data')
        if data is not None and ('month' in data or 'year' in data):
            data = data.copy()
            data.setdefault('thang', data.get('month', ''))
            data.setdefault('nam', data.get('year', ''))
            if args:
                args = (data, *args[1:])
            else:
                kwargs['data'] = data
        super().__init__(*args, **kwargs)
        hom_nay = timezone.localdate()
        self.fields['thang'].initial = hom_nay.month
        self.fields['nam'].initial = hom_nay.year



class BoLocPhieuLuong(forms.Form):
    thang = forms.IntegerField(min_value=1, max_value=12, label='Tháng')
    nam = forms.IntegerField(min_value=2000, max_value=2100, label='Năm')

    def __init__(self, *args, **kwargs):
        data = args[0] if args else kwargs.get('data')
        if data is not None and ('month' in data or 'year' in data):
            data = data.copy()
            data.setdefault('thang', data.get('month', ''))
            data.setdefault('nam', data.get('year', ''))
            if args:
                args = (data, *args[1:])
            else:
                kwargs['data'] = data
        super().__init__(*args, **kwargs)
        hom_nay = timezone.localdate()
        self.fields['thang'].initial = hom_nay.month
        self.fields['nam'].initial = hom_nay.year
