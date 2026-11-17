from django import forms
from django.utils import timezone

from nhan_vien.access import nhan_vien_duoc_hien_thi
from nhan_vien.models import PhongBan, NhanVien


class BoLocKy(forms.Form):
    thang = forms.IntegerField(label='Tháng', min_value=1, max_value=12)
    nam = forms.IntegerField(label='Năm', min_value=2000, max_value=2100)
    nhan_vien = forms.ModelChoiceField(label='Nhân viên', queryset=NhanVien.objects.none(), required=False)
    phong_ban = forms.ModelChoiceField(label='Phòng ban', queryset=PhongBan.objects.none(), required=False)

    def __init__(self, nguoi_dung, data=None):
        hom_nay = timezone.localdate()
        du_lieu_gui_len = (data.dict() if hasattr(data, 'dict') else dict(data)) if data else {}
        gia_tri_mac_dinh = {'thang': hom_nay.month, 'nam': hom_nay.year, **du_lieu_gui_len}
        # Chấp nhận tên tham số cũ để các liên kết đã phát hành tiếp tục hoạt động.
        for ten_moi, ten_cu in (('thang', 'month'), ('nam', 'year'),
                                ('nhan_vien', 'employee'), ('phong_ban', 'department')):
            if ten_moi not in du_lieu_gui_len and ten_cu in du_lieu_gui_len:
                gia_tri_mac_dinh[ten_moi] = du_lieu_gui_len[ten_cu]
        super().__init__(gia_tri_mac_dinh)
        danh_sach_nhan_vien = nhan_vien_duoc_hien_thi(nguoi_dung)
        self.fields['nhan_vien'].queryset = danh_sach_nhan_vien
        self.fields['phong_ban'].queryset = PhongBan.objects.filter(
            pk__in=danh_sach_nhan_vien.values('phong_ban_id')
        )

    def nhan_vien_trong_pham_vi(self, nguoi_dung):
        danh_sach_nhan_vien = nhan_vien_duoc_hien_thi(nguoi_dung)
        if self.cleaned_data.get('nhan_vien'):
            danh_sach_nhan_vien = danh_sach_nhan_vien.filter(pk=self.cleaned_data['nhan_vien'].pk)
        if self.cleaned_data.get('phong_ban'):
            danh_sach_nhan_vien = danh_sach_nhan_vien.filter(phong_ban=self.cleaned_data['phong_ban'])
        return danh_sach_nhan_vien

    def clean(self):
        du_lieu = super().clean()
        # Giữ khóa tiếng Anh để tương thích với code bảng công và liên kết hiện có.
        for ten_cu, ten_moi in (('month', 'thang'), ('year', 'nam'),
                                ('employee', 'nhan_vien'), ('department', 'phong_ban')):
            if ten_moi in du_lieu:
                du_lieu[ten_cu] = du_lieu[ten_moi]
        return du_lieu


def _truong_ngay(label):
    return forms.DateField(
        label=label, required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )


class BoLocBangCong(BoLocKy):
    day = _truong_ngay('Ngày chấm công')
    day_state = forms.ChoiceField(
        label='Chấm công trong ngày', required=False,
        choices=[('', 'Tất cả'), ('ontime', 'Đúng giờ'), ('late', 'Đi trễ'), ('unchecked', 'Chưa check-in')],
    )
    q = forms.CharField(
        label='Từ khóa (Họ tên)', required=False, max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Tìm theo họ hoặc tên...'}),
    )
    review = forms.ChoiceField(
        label='Trạng thái', required=False,
        choices=[('', 'Tất cả'), ('approved', 'Đã duyệt'), ('pending', 'Chờ duyệt'),
                 ('incomplete', 'Cần kiểm tra'), ('empty', 'Chưa có dữ liệu')],
    )

    def __init__(self, user, data=None):
        super().__init__(user, data)
        self.fields['thang'].widget = forms.Select(choices=[
            (month, f'Tháng {month:02}') for month in range(1, 13)
        ])
        self.fields['nam'].widget = forms.Select(choices=[
            (year, f'Năm {year}') for year in range(2000, 2101)
        ])
        self.fields['phong_ban'].empty_label = 'Tất cả'

    def clean(self):
        data = super().clean()
        day = data.get('day')
        if data.get('day_state') and not day:
            raise forms.ValidationError('Cần chọn ngày chấm công.')
        if day and (day.month, day.year) != (data.get('month'), data.get('year')):
            raise forms.ValidationError('Ngày chấm công phải thuộc tháng/năm đã chọn.')
        return data
