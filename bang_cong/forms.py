"""Form lọc bảng công, xem lịch sử và nhập/chỉnh sửa chấm công."""

from django import forms  # Các trường nhập, widget và kiểm tra dữ liệu form.

from nhan_vien.access import nhan_vien_duoc_hien_thi  # Phạm vi nhân viên được phép xem.
from nhan_vien.filters import BoLocKy  # Bộ lọc kỳ/phòng ban dùng chung.

from .models import ChamCong  # Model dùng để tạo form nhập công.


def _truong_ngay(nhan):
    # Tạo trường ngày không bắt buộc; widget mở ô chọn ngày của trình duyệt.
    return forms.DateField(label=nhan, required=False, widget=forms.DateInput(attrs={'type': 'date'}))


def _kiem_tra_khoang_ngay(du_lieu, thong_bao):
    # get() trả None nếu chưa có giá trị; chỉ so sánh khi nhập đủ hai đầu.
    bat_dau, ket_thuc = du_lieu.get('start'), du_lieu.get('end')
    if bat_dau and ket_thuc and bat_dau > ket_thuc:
        raise forms.ValidationError(thong_bao)
    return du_lieu  # Trả dữ liệu đã kiểm tra cho clean().


class BoLocBangCong(BoLocKy):
    """Kế thừa lọc kỳ/phòng ban và thêm điều kiện tìm bảng công."""
    # Tên trường giữ nguyên để khớp GET, view và template hiện tại.
    # required=False cho phép bỏ trống; label là nhãn hiển thị.
    day = _truong_ngay('Ngày chấm công')
    # Lọc đúng giờ, trễ hoặc chưa check-in trong ngày đã chọn.
    day_state = forms.ChoiceField(label='Chấm công trong ngày', required=False,
        choices=[('', 'Tất cả'), ('ontime', 'Đúng giờ'), ('late', 'Đi trễ'), ('unchecked', 'Chưa check-in')])
    # Từ khóa tối đa 150 ký tự; placeholder là lời gợi ý trong ô tìm kiếm.
    q = forms.CharField(label='Từ khóa (Họ tên)', required=False, max_length=150,
                        widget=forms.TextInput(attrs={'placeholder': 'Tìm theo họ hoặc tên...'}))
    # Trạng thái tổng hợp; choices gồm mã lưu và nhãn hiển thị.
    review = forms.ChoiceField(label='Trạng thái', required=False, choices=[('', 'Tất cả'),
        ('approved', 'Đã duyệt'), ('pending', 'Chờ duyệt'), ('incomplete', 'Cần kiểm tra'), ('empty', 'Chưa có dữ liệu')])

    def __init__(self, user, data=None):
        # Khởi tạo bộ lọc cha với tài khoản và dữ liệu gửi lên.
        super().__init__(user, data)
        # Danh sách tháng 01–12; :02 thêm số 0 trước tháng có một chữ số.
        self.fields['thang'].widget = forms.Select(choices=[(thang, f'Tháng {thang:02}') for thang in range(1, 13)])
        # range không lấy mốc cuối: các năm từ 2000 đến 2100.
        self.fields['nam'].widget = forms.Select(choices=[(nam, f'Năm {nam}') for nam in range(2000, 2101)])
        # Đặt nhãn lựa chọn phòng ban trống, vẫn giữ phạm vi quyền của bộ lọc cha.
        self.fields['phong_ban'].empty_label = 'Tất cả'

    def clean(self):
        # Chạy kiểm tra của lớp cha, rồi kiểm tra quan hệ giữa các trường.
        du_lieu = super().clean()
        ngay = du_lieu.get('day')
        # Lọc tình trạng check-in phải đi kèm một ngày cụ thể.
        if du_lieu.get('day_state') and not ngay:
            raise forms.ValidationError('Cần chọn ngày chấm công.')
        # Ngày lọc phải nằm trong tháng/năm đã chọn.
        if ngay and (ngay.month, ngay.year) != (du_lieu.get('month'), du_lieu.get('year')):
            raise forms.ValidationError('Ngày chấm công phải thuộc tháng/năm đã chọn.')
        return du_lieu


# Ánh xạ khóa dữ liệu lịch sử sang tên dễ đọc trên giao diện.
# Giữ các khóa cũ để đọc được lịch sử đã lưu, kể cả trường ghi chú đã bỏ khỏi form.
class ChamCongForm(forms.ModelForm):
    """Form ghi nhận một bản công mới."""

    class Meta:
        model = ChamCong
        fields = ['nhan_vien', 'ngay', 'gio_vao', 'gio_ra', 'trang_thai']
        widgets = {
            'ngay': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'gio_vao': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'gio_ra': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nhan_vien'].queryset = nhan_vien_duoc_hien_thi(user)