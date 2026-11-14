from django import forms
from django.contrib.auth import get_user_model

from nhan_vien.access import visible_employees
from nhan_vien.filters import PeriodFilter

from .models import ChamCong


def _truong_ngay(nhan):
    return forms.DateField(label=nhan, required=False, widget=forms.DateInput(attrs={'type': 'date'}))


def _kiem_tra_khoang_ngay(du_lieu, thong_bao):
    bat_dau, ket_thuc = du_lieu.get('start'), du_lieu.get('end')
    if bat_dau and ket_thuc and bat_dau > ket_thuc:
        raise forms.ValidationError(thong_bao)
    return du_lieu


class BoLocBangCong(PeriodFilter):
    day = _truong_ngay('Ngày chấm công')
    day_state = forms.ChoiceField(label='Chấm công trong ngày', required=False,
        choices=[('', 'Tất cả'), ('ontime', 'Đúng giờ'), ('late', 'Đi trễ'), ('unchecked', 'Chưa check-in')])
    q = forms.CharField(label='Từ khóa (Họ tên)', required=False, max_length=150,
                        widget=forms.TextInput(attrs={'placeholder': 'Tìm theo họ hoặc tên...'}))
    review = forms.ChoiceField(label='Trạng thái', required=False, choices=[('', 'Tất cả'),
        ('approved', 'Đã duyệt'), ('pending', 'Chờ duyệt'), ('incomplete', 'Cần kiểm tra'), ('empty', 'Chưa có dữ liệu')])

    def __init__(self, user, data=None):
        super().__init__(user, data)
        self.fields['month'].widget = forms.Select(choices=[(thang, f'Tháng {thang:02}') for thang in range(1, 13)])
        self.fields['year'].widget = forms.Select(choices=[(nam, f'Năm {nam}') for nam in range(2000, 2101)])
        self.fields['department'].empty_label = 'Tất cả'

    def clean(self):
        du_lieu = super().clean()
        ngay = du_lieu.get('day')
        if du_lieu.get('day_state') and not ngay:
            raise forms.ValidationError('Cần chọn ngày chấm công.')
        if ngay and (ngay.month, ngay.year) != (du_lieu.get('month'), du_lieu.get('year')):
            raise forms.ValidationError('Ngày chấm công phải thuộc tháng/năm đã chọn.')
        return du_lieu


class BoLocCongNgay(BoLocBangCong):
    state = forms.ChoiceField(label='Tình trạng', required=False, choices=[('', 'Tất cả'),
        ('paid', 'Có công hưởng lương'), ('actual', 'Có công thực tế'), ('paid_leave', 'Nghỉ hưởng lương'),
        ('late', 'Đi trễ'), ('leave', 'Nghỉ phép'), ('absent', 'Nghỉ không phép'),
        ('incomplete', 'Thiếu dữ liệu'), ('ot', 'Có tăng ca')])
    start = _truong_ngay('Ngày bắt đầu')
    end = _truong_ngay('Ngày kết thúc')

    def clean(self):
        return _kiem_tra_khoang_ngay(super().clean(), 'Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.')


CAC_TRUONG_DIEU_CHINH = {'overtime_hours': 'Giờ OT tự động', 'check_in': 'Giờ vào ca', 'check_out': 'Giờ ra ca', 'status': 'Tình trạng',
    'work_hours': 'Tổng giờ làm', 'late_minutes': 'Đi trễ (phút)', 'actual_units': 'Công thực tế',
    'paid_leave_units': 'Nghỉ hưởng lương', 'paid_units': 'Công hưởng lương', 'note': 'Ghi chú'}


class BoLocLichSuCong(forms.Form):
    start = _truong_ngay('Từ ngày điều chỉnh')
    end = _truong_ngay('Đến ngày điều chỉnh')
    field = forms.ChoiceField(label='Trường điều chỉnh', choices=[('', 'Tất cả'), *CAC_TRUONG_DIEU_CHINH.items()], required=False)
    actor = forms.ModelChoiceField(label='Người điều chỉnh', queryset=get_user_model().objects.none(), required=False,
                                  empty_label='Tất cả')

    def __init__(self, data, logs):
        super().__init__(data)
        self.fields['actor'].queryset = get_user_model().objects.filter(
            pk__in=logs.values_list('nguoi_thuc_hien_id', flat=True),
        ).order_by('username')

    def clean(self):
        return _kiem_tra_khoang_ngay(super().clean(), 'Khoảng ngày điều chỉnh không hợp lệ.')


class ChamCongForm(forms.ModelForm):
    reason = forms.CharField(label='Lý do tạo/chỉnh sửa', widget=forms.Textarea)

    class Meta:
        model = ChamCong
        fields = ['nhan_vien', 'ngay', 'gio_vao', 'gio_ra', 'trang_thai', 'ghi_chu']
        widgets = {'ngay': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'gio_vao': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
                   'gio_ra': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M')}

    def __init__(self, user, *args, **kwargs):
        # Nhận cả tên POST/initial cũ để các liên kết, biểu mẫu đang mở vẫn dùng được.
        ten_truong_cu = {'employee': 'nhan_vien', 'date': 'ngay', 'check_in': 'gio_vao',
                   'check_out': 'gio_ra', 'status': 'trang_thai', 'note': 'ghi_chu'}
        if args and args[0] is not None:
            du_lieu = args[0].copy()
            for cu, moi in ten_truong_cu.items():
                if cu in du_lieu and moi not in du_lieu:
                    du_lieu[moi] = du_lieu[cu]
            args = (du_lieu, *args[1:])
        if kwargs.get('initial'):
            kwargs['initial'] = {ten_truong_cu.get(khoa, khoa): gia_tri for khoa, gia_tri in kwargs['initial'].items()}
        super().__init__(*args, **kwargs)
        self.fields['nhan_vien'].queryset = visible_employees(user)
        if self.instance.pk:
            for truong in ('nhan_vien', 'ngay'):
                self.fields[truong].disabled = True
