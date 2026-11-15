from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import DonNghiPhep


# Giới hạn và loại tệp minh chứng được phép tải lên.
KICH_THUOC_TEP_TOI_DA = 5 * 1024 * 1024
CAC_LOAI_TEP_CHO_PHEP = {
    'image/jpeg', 'image/png', 'image/webp', 'image/gif', 'application/pdf',
}
# Danh sách định dạng cho trình duyệt lọc khi người dùng chọn tệp.
DINH_DANG_TEP_CHO_PHEP = (
    '.jpg,.jpeg,.png,.webp,.gif,.pdf,'
    'image/jpeg,image/png,image/webp,image/gif,application/pdf'
)


def kiem_tra_tep(tep_tai_len):
    """Kiểm tra kích thước và định dạng của tệp minh chứng."""
    if not tep_tai_len:
        return tep_tai_len
    if tep_tai_len.size > KICH_THUOC_TEP_TOI_DA:
        raise ValidationError('Tệp minh chứng không được vượt quá 5 MB.')
    if tep_tai_len.content_type not in CAC_LOAI_TEP_CHO_PHEP:
        raise ValidationError('Vui lòng tải lên ảnh JPG, PNG, WEBP, GIF hoặc tệp PDF.')
    return tep_tai_len


class DonNghiPhepForm(forms.ModelForm):
    """Biểu mẫu tạo đơn nghỉ phép từ các trường trong model DonNghiPhep."""
    def __init__(self, data=None, files=None, nhan_vien=None):
        super().__init__(data=data, files=files)
        # Gắn nhân viên vào đơn để model có đủ thông tin khi kiểm tra dữ liệu.
        if nhan_vien and not self.instance.nhan_vien_id:
            self.instance.nhan_vien = nhan_vien

    class Meta:
        model = DonNghiPhep
        fields = ['ngay_bat_dau', 'ngay_ket_thuc', 'loai_nghi', 'ly_do', 'tep_dinh_kem']
        # Chỉnh kiểu hiển thị của các ô nhập trên trang web.
        widgets = {
            'ngay_bat_dau': forms.DateInput(attrs={'type': 'date', 'class': 'leave-input'}),
            'ngay_ket_thuc': forms.DateInput(attrs={'type': 'date', 'class': 'leave-input'}),
            'loai_nghi': forms.Select(attrs={'class': 'leave-input'}),
            'ly_do': forms.Textarea(attrs={
                'class': 'leave-input', 'rows': 3,
                'placeholder': 'Nhập lý do xin nghỉ phép',
            }),
            'tep_dinh_kem': forms.ClearableFileInput(attrs={
                'accept': DINH_DANG_TEP_CHO_PHEP, 'class': 'leave-file-input',
            }),
        }

    def clean_tep_dinh_kem(self):
        return kiem_tra_tep(self.cleaned_data.get('tep_dinh_kem'))

    def clean(self):
        # Kiểm tra thêm những điều kiện liên quan đến form trước khi gửi đơn.
        du_lieu = super().clean()
        if not self.instance.nhan_vien_id:
            raise ValidationError('Không xác định được nhân viên đăng ký nghỉ.')

        ngay_bat_dau = du_lieu.get('ngay_bat_dau')
        if ngay_bat_dau and ngay_bat_dau < timezone.localdate():
            self.add_error('ngay_bat_dau', 'Ngày bắt đầu nghỉ không được ở quá khứ.')
        return du_lieu


class TepMinhChungForm(forms.Form):
    """Biểu mẫu tải minh chứng bổ sung cho đơn đã tạo."""
    tep_dinh_kem = forms.FileField(
        label='Ảnh minh chứng',
        widget=forms.ClearableFileInput(attrs={'accept': DINH_DANG_TEP_CHO_PHEP}),
    )

    def clean_tep_dinh_kem(self):
        return kiem_tra_tep(self.cleaned_data.get('tep_dinh_kem'))


class LocDonNghiPhepForm(forms.Form):
    """Các bộ lọc danh sách đơn; tên trường giữ nguyên để khớp URL và giao diện."""
    q = forms.CharField(required=False, label='Từ khóa')
    department = forms.IntegerField(required=False, widget=forms.Select(), label='Phòng ban')
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'Tất cả trạng thái'), *DonNghiPhep.CAC_TRANG_THAI],
        label='Trạng thái',
    )
    leave_type = forms.ChoiceField(
        required=False,
        choices=[('', 'Tất cả loại nghỉ'), *DonNghiPhep.LOAI_NGHI],
        label='Loại nghỉ',
    )
    start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}), label='Từ ngày')
    end_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}), label='Đến ngày')

    def __init__(self, cac_phong_ban, data=None):
        super().__init__(data=data)
        # Đưa các phòng ban được phép xem vào danh sách lựa chọn.
        self.fields['department'].widget = forms.Select(choices=[
            ('', 'Tất cả phòng ban'),
            *((phong_ban.pk, phong_ban.name) for phong_ban in cac_phong_ban),
        ])
