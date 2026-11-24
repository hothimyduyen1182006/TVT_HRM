from django import forms

from nhan_vien.models import PhongBan

from .models import Luong


class BoLocPhieuLuong(forms.Form):
    thang = forms.IntegerField(
        min_value=1, max_value=12, label='Tháng',
    )
    nam = forms.IntegerField(
        min_value=2000, max_value=2100, label='Năm',
    )


class BoLocBangLuong(BoLocPhieuLuong):
    tu_khoa = forms.CharField(
        required=False, max_length=150, label='Nhân viên',
    )
    phong_ban = forms.ModelChoiceField(
        queryset=PhongBan.objects.all(),
        required=False,
        label='Phòng ban',
    )
    trang_thai = forms.ChoiceField(
        required=False,
        label='Trạng thái',
        choices=[
            ('', 'Tất cả'),
            *Luong._meta.get_field('trang_thai').choices,
        ],
    )
