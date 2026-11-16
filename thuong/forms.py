import re

from django import forms
from django.utils import timezone

from nhan_vien.access import nhan_vien_duoc_hien_thi
from nhan_vien.models import PhongBan, NhanVien

from .models import Thuong


def chon_ky_thuong(cac_truong, nam_hien_tai, nhan_thang='Tất cả', nhan_nam='Tất cả'):
    cac_truong['thang'].widget = forms.Select(choices=[('', nhan_thang)] + [
        (thang, f'Tháng {thang:02}') for thang in range(1, 13)
    ])
    cac_truong['nam'].widget = forms.Select(choices=[('', nhan_nam)] + [
        (nam, f'Năm {nam}') for nam in range(2000, nam_hien_tai + 2)
    ])


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


class BonusFilter(forms.Form):
    thang = forms.IntegerField(label='Tháng', min_value=1, max_value=12, required=False)
    nam = forms.IntegerField(label='Năm', min_value=2000, max_value=2100, required=False)
    nhan_vien = forms.ModelChoiceField(label='Nhân viên', queryset=NhanVien.objects.none(), required=False)
    phong_ban = forms.ModelChoiceField(label='Phòng ban', queryset=PhongBan.objects.none(), required=False)
    tu_khoa = forms.CharField(
        label='Từ khóa (Họ tên)',
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Tìm theo họ hoặc tên...'}),
    )
    trang_thai = forms.ChoiceField(
        label='Trạng thái', required=False, choices=[('', 'Tất cả'), *Thuong.STATUSES]
    )

    def __init__(self, nguoi_dung, data=None, default_current_period=False):
        today = timezone.localdate()
        if default_current_period:
            if data:
                data = data.copy()
                data.setdefault('thang', today.month)
                data.setdefault('nam', today.year)
            else:
                data = {'thang': today.month, 'nam': today.year}
        super().__init__(data=data)
        chon_ky_thuong(self.fields, timezone.localdate().year)
        nhan_vien_hien = nhan_vien_duoc_hien_thi(nguoi_dung)
        self.fields['nhan_vien'].queryset = nhan_vien_hien
        self.fields['phong_ban'].queryset = PhongBan.objects.filter(
            pk__in=nhan_vien_hien.values('phong_ban_id')
        )
        self.fields['nhan_vien'].empty_label = 'Tất cả'
        self.fields['phong_ban'].empty_label = 'Tất cả'

    def pham_vi_nhan_vien(self, nguoi_dung):
        pham_vi = nhan_vien_duoc_hien_thi(nguoi_dung)
        if self.cleaned_data.get('nhan_vien'):
            pham_vi = pham_vi.filter(pk=self.cleaned_data['nhan_vien'].pk)
        if self.cleaned_data.get('phong_ban'):
            pham_vi = pham_vi.filter(phong_ban=self.cleaned_data['phong_ban'])
        return pham_vi


class PersonalBonusFilter(forms.Form):
    thang = forms.IntegerField(label='Tháng', min_value=1, max_value=12, required=False)
    nam = forms.IntegerField(label='Năm', min_value=2000, max_value=2100, required=False)
    trang_thai = forms.ChoiceField(label='Trạng thái', required=False,
                               choices=[('', 'Tất cả'), *Thuong.STATUSES])

    def __init__(self, data=None):
        today = timezone.localdate()
        if data is None:
            super().__init__(initial={'thang': today.month, 'nam': today.year})
        else:
            du_lieu_co_the_sua = data.copy()
            du_lieu_co_the_sua.setdefault('thang', today.month)
            du_lieu_co_the_sua.setdefault('nam', today.year)
            super().__init__(data=du_lieu_co_the_sua)
        chon_ky_thuong(self.fields, today.year)


class BonusProposalForm(forms.Form):
    thang = forms.IntegerField(label='Tháng', min_value=1, max_value=12)
    nam = forms.IntegerField(label='Năm', min_value=2000, max_value=2100)
    nhan_vien = forms.ModelChoiceField(label='Nhân viên', queryset=NhanVien.objects.none())
    ten = forms.CharField(label='Tên khoản thưởng khác', max_length=100, required=False)
    ly_do = forms.CharField(label='Lý do đề xuất', widget=forms.Textarea(attrs={'rows': 3}), required=False)
    so_tien = VNDField(
        label='Số tiền (VNĐ)',
        min_value=0,
        max_digits=12,
        decimal_places=0,
        required=False,
    )

    def __init__(self, nguoi_dung, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nhan_vien'].queryset = nhan_vien_duoc_hien_thi(nguoi_dung).filter(dang_hoat_dong=True)
        self.fields['nhan_vien'].label_from_instance = (
            lambda item: f'{item.ma_ho_so} · {item.ho_va_ten} · {item.phong_ban.ten_phong_ban}'
        )
        self.fields['nhan_vien'].empty_label = 'Chọn nhân viên'
        self.fields['ten'].widget.attrs['placeholder'] = 'Ví dụ: Thưởng dự án'
        self.fields['ly_do'].widget.attrs.update({
            'rows': 4,
            'placeholder': 'Nêu ngắn gọn căn cứ và thành tích được đề xuất thưởng.',
        })
        self.fields['so_tien'].widget = forms.TextInput(attrs={
            'placeholder': 'Ví dụ: 500000',
            'inputmode': 'numeric',
            'autocomplete': 'off',
        })
        today = timezone.localdate()
        chon_ky_thuong(self.fields, today.year, 'Chọn tháng', 'Chọn năm')

    def clean(self):
        du_lieu = super().clean()
        du_lieu['ten'] = (du_lieu.get('ten') or '').strip()
        du_lieu['ly_do'] = (du_lieu.get('ly_do') or '').strip()
        if not all((du_lieu.get('ten'), du_lieu.get('ly_do'), du_lieu.get('so_tien') is not None)):
            raise forms.ValidationError('Đề xuất thưởng khác cần có tên thưởng, lý do và số tiền.')
        return du_lieu
