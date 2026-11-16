"""Form lọc bảng công, xem lịch sử và nhập/chỉnh sửa chấm công."""

from django import forms  # Các trường nhập, widget và kiểm tra dữ liệu form.
from django.contrib.auth import get_user_model  # Lấy model tài khoản đang cấu hình.

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
CAC_TRUONG_DIEU_CHINH = {'overtime_hours': 'Giờ OT tự động', 'check_in': 'Giờ vào ca', 'check_out': 'Giờ ra ca', 'status': 'Tình trạng',
    'work_hours': 'Tổng giờ làm', 'late_minutes': 'Đi trễ (phút)', 'actual_units': 'Công thực tế',
    'paid_leave_units': 'Nghỉ hưởng lương', 'paid_units': 'Công hưởng lương', 'note': 'Ghi chú'}


class BoLocLichSuCong(forms.Form):
    """Lọc lịch sử theo ngày sửa, trường thay đổi và người thực hiện."""
    # Đây là ngày điều chỉnh, khác với ngày nhân viên chấm công.
    start = _truong_ngay('Từ ngày điều chỉnh')
    end = _truong_ngay('Đến ngày điều chỉnh')
    # Dấu * đưa các cặp mã/nhãn trong từ điển vào danh sách lựa chọn.
    field = forms.ChoiceField(label='Trường điều chỉnh', choices=[('', 'Tất cả'), *CAC_TRUONG_DIEU_CHINH.items()], required=False)
    # ModelChoiceField chọn một tài khoản; ban đầu chưa nạp tài khoản nào.
    actor = forms.ModelChoiceField(label='Người điều chỉnh', queryset=get_user_model().objects.none(), required=False,
                                  empty_label='Tất cả')

    def __init__(self, data, logs):
        # data là dữ liệu lọc; logs là tập lịch sử đã giới hạn theo phạm vi được xem.
        super().__init__(data)
        # Chỉ hiện tài khoản xuất hiện trong lịch sử; sắp theo tên đăng nhập.
        # values_list(..., flat=True) lấy danh sách mã người thực hiện.
        self.fields['actor'].queryset = get_user_model().objects.filter(
            pk__in=logs.values_list('nguoi_thuc_hien_id', flat=True),
        ).order_by('username')

    def clean(self):
        # Không nhận khoảng thời gian có ngày bắt đầu sau ngày kết thúc.
        return _kiem_tra_khoang_ngay(super().clean(), 'Khoảng ngày điều chỉnh không hợp lệ.')


class ChamCongForm(forms.ModelForm):
    """Form tạo/sửa bản công; ModelForm sử dụng kiểm tra dữ liệu của model."""
    # Lý do là trường bắt buộc của form, service dùng ghi lịch sử; không là cột ChamCong.
    reason = forms.CharField(label='Lý do tạo/chỉnh sửa', widget=forms.Textarea)

    class Meta:
        # Model liên kết và những trường được phép nhập/sửa trên form.
        model = ChamCong
        fields = ['nhan_vien', 'ngay', 'gio_vao', 'gio_ra', 'trang_thai']
        # Kiểu ô nhập và định dạng: năm-tháng-ngày, giờ:phút.
        widgets = {'ngay': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'gio_vao': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
                   'gio_ra': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M')}

    def __init__(self, user, *args, **kwargs):
        # user dùng giới hạn nhân viên; *args/**kwargs nhận tham số khởi tạo của form.
        # Nhận cả tên POST/initial cũ để các liên kết, biểu mẫu đang mở vẫn dùng được.
        ten_truong_cu = {'employee': 'nhan_vien', 'date': 'ngay', 'check_in': 'gio_vao',
                   'check_out': 'gio_ra', 'status': 'trang_thai', 'note': 'ghi_chu'}
        # Sao chép dữ liệu gửi lên vì QueryDict ban đầu có thể không cho chỉnh sửa.
        if args and args[0] is not None:
            du_lieu = args[0].copy()
            for cu, moi in ten_truong_cu.items():
                # Chỉ bổ sung tên mới khi chưa có, không ghi đè dữ liệu tên mới.
                if cu in du_lieu and moi not in du_lieu:
                    du_lieu[moi] = du_lieu[cu]
            args = (du_lieu, *args[1:])  # Thay dữ liệu đã đổi tên, giữ các tham số còn lại.
        # initial là dữ liệu điền sẵn; đổi tên khóa cũ tương tự dữ liệu POST.
        if kwargs.get('initial'):
            kwargs['initial'] = {ten_truong_cu.get(khoa, khoa): gia_tri for khoa, gia_tri in kwargs['initial'].items()}
        super().__init__(*args, **kwargs)  # Tạo các trường ModelForm trước khi cấu hình.
        # Chỉ cho chọn nhân viên thuộc phạm vi quyền của tài khoản.
        self.fields['nhan_vien'].queryset = nhan_vien_duoc_hien_thi(user)
        # Có khóa chính nghĩa là sửa bản ghi đã tồn tại: cố định nhân viên và ngày.
        if self.instance.pk:
            for truong in ('nhan_vien', 'ngay'):
                # Django bỏ qua giá trị gửi lên cho trường disabled, dùng giá trị ban đầu.
                self.fields[truong].disabled = True
