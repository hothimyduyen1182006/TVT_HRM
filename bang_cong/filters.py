from django import forms
from django.utils import timezone

from nhan_vien.access import nhan_vien_duoc_hien_thi
from nhan_vien.models import PhongBan


class BoLocBangCong(forms.Form):
    thang = forms.IntegerField(label='Tháng', min_value=1, max_value=12)
    nam = forms.IntegerField(label='Năm', min_value=2000, max_value=2100)
    phong_ban = forms.ModelChoiceField(label='Phòng ban', queryset=PhongBan.objects.none(), required=False)
    ngay_cham_cong = forms.DateField(
        label='Ngày chấm công', required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    trang_thai_cham_cong = forms.ChoiceField(
        label='Chấm công trong ngày', required=False,
        choices=[('', 'Tất cả'), ('ontime', 'Đúng giờ'), ('late', 'Đi trễ'), ('unchecked', 'Chưa check-in')],
    )
    tu_khoa = forms.CharField(
        label='Từ khóa (Họ tên)', required=False, max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Tìm theo họ hoặc tên...'}),
    )
    trang_thai = forms.ChoiceField(
        label='Trạng thái', required=False,
        choices=[('', 'Tất cả'), ('approved', 'Đã duyệt'), ('pending', 'Chờ duyệt'),
                 ('incomplete', 'Cần kiểm tra'), ('empty', 'Chưa có dữ liệu')],
    )

    def __init__(self, nguoi_dung, du_lieu=None):
        hom_nay = timezone.localdate()
        du_lieu_gui_len = (du_lieu.dict() if hasattr(du_lieu, 'dict') else dict(du_lieu)) if du_lieu else {}
        gia_tri_mac_dinh = {'thang': hom_nay.month, 'nam': hom_nay.year, **du_lieu_gui_len}
        super().__init__(gia_tri_mac_dinh)
        danh_sach_nhan_vien = nhan_vien_duoc_hien_thi(nguoi_dung)
        self.fields['phong_ban'].queryset = PhongBan.objects.filter(
            pk__in=danh_sach_nhan_vien.values('phong_ban_id')
        )
        self.fields['thang'].widget = forms.Select(choices=[
            (thang, f'Tháng {thang:02}') for thang in range(1, 13)
        ])
        self.fields['nam'].widget = forms.Select(choices=[
            (nam, f'Năm {nam}') for nam in range(2000, 2101)
        ])
        self.fields['phong_ban'].empty_label = 'Tất cả'

    def nhan_vien_trong_pham_vi(self, nguoi_dung):
        danh_sach_nhan_vien = nhan_vien_duoc_hien_thi(nguoi_dung)
        if self.cleaned_data.get('phong_ban'):
            danh_sach_nhan_vien = danh_sach_nhan_vien.filter(phong_ban=self.cleaned_data['phong_ban'])
        return danh_sach_nhan_vien

    def clean(self):
        du_lieu = super().clean()
        ngay_cham_cong = du_lieu.get('ngay_cham_cong')
        if du_lieu.get('trang_thai_cham_cong') and not ngay_cham_cong:
            raise forms.ValidationError('Cần chọn ngày chấm công.')
        ky_da_chon = (du_lieu.get('thang'), du_lieu.get('nam'))
        if ngay_cham_cong and (ngay_cham_cong.month, ngay_cham_cong.year) != ky_da_chon:
            raise forms.ValidationError('Ngày chấm công phải thuộc tháng/năm đã chọn.')
        return du_lieu
