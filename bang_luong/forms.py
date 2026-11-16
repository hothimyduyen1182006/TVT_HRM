from django import forms
from nhan_vien.filters import BoLocKy
from django.utils import timezone


class BoLocBangLuong(BoLocKy):
    q = forms.CharField(label='Từ khóa (Họ tên / ID)', required=False, max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Tìm theo họ tên hoặc ID...'}))
    status = forms.ChoiceField(label='Trạng thái', required=False,
        choices=[('', 'Tất cả'), ('pending', 'Chờ HR kiểm tra'), ('submitted', 'Chờ Giám đốc ký duyệt'),
                 ('approved', 'Đã duyệt'), ('paid', 'Đã chi trả')])

    def __init__(self, user, data=None):
        super().__init__(user, data)
        self.fields['phong_ban'].empty_label = 'Tất cả'
        thiet_lap_bo_chon_ky(self)


def thiet_lap_bo_chon_ky(form):
    truong_thang = 'thang' if 'thang' in form.fields else 'month'
    truong_nam = 'nam' if 'nam' in form.fields else 'year'
    form.fields[truong_thang].widget = forms.Select(choices=[(thang, f'Tháng {thang:02}') for thang in range(1, 13)])
    form.fields[truong_nam].widget = forms.Select(choices=[(nam, f'Năm {nam}') for nam in range(2000, 2101)])


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
