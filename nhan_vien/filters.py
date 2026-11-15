from django import forms
from django.utils import timezone

from .access import nhan_vien_duoc_hien_thi
from .models import PhongBan, NhanVien


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
        # Giữ khóa dữ liệu nội bộ cũ cho các dịch vụ lương, công và thưởng đang dùng chung.
        for ten_cu, ten_moi in (('month', 'thang'), ('year', 'nam'),
                                ('employee', 'nhan_vien'), ('department', 'phong_ban')):
            if ten_moi in du_lieu:
                du_lieu[ten_cu] = du_lieu[ten_moi]
        return du_lieu
