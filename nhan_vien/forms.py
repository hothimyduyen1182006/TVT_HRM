from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from decimal import Decimal
from django.db.models import Q
from .access import NHAN_SU, GIAM_DOC, TRUONG_PHONG, co_vai_tro

from .models import HocVan, NhanVien, HopDongLaoDong, PhongBan, ChucVu


class BoLocNhanVien(forms.Form):
    """Các ô lọc, kiểm tra dữ liệu và thu hẹp danh sách nhân viên đã được cấp quyền."""

    q = forms.CharField(label='Họ tên / Mã NV', required=False, max_length=100)
    department = forms.ModelChoiceField(label='Phòng ban', queryset=PhongBan.objects.none(), required=False)
    position = forms.ModelChoiceField(label='Chức vụ', queryset=ChucVu.objects.none(), required=False)
    status = forms.ChoiceField(label='Tình trạng làm việc', required=False,
                              choices=[('', 'Tất cả trạng thái'), *NhanVien.EMPLOYMENT_STATUS_CHOICES])
    hire_from = forms.DateField(label='Vào làm từ ngày', required=False,
                               widget=forms.DateInput(attrs={'type': 'date'}))
    hire_to = forms.DateField(label='Vào làm đến ngày', required=False,
                             widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, nguoi_dung, data=None):
        du_lieu = data.copy() if data is not None else {}
        for ten in self.base_fields:
            du_lieu[ten] = du_lieu.get(ten, '').strip()
        du_lieu['q'] = du_lieu['q'][:100]
        super().__init__(data=du_lieu)
        # Giữ cùng phạm vi lựa chọn phòng ban/chức vụ như trang nhân viên.
        phong_ban = PhongBan.objects.all()
        if co_vai_tro(nguoi_dung, TRUONG_PHONG) and not co_vai_tro(nguoi_dung, NHAN_SU, GIAM_DOC):
            phong_ban = phong_ban.filter(truong_phong__nguoi_dung=nguoi_dung)
        self.fields['department'].queryset = phong_ban.distinct()
        self.fields['position'].queryset = ChucVu.objects.select_related('phong_ban').filter(phong_ban__in=phong_ban)

    def loc_danh_sach(self, danh_sach):
        # Danh sách đầu vào đã được view giới hạn theo quyền; form chỉ thu hẹp thêm.
        if not self.is_valid():
            return danh_sach.none()
        du_lieu = self.cleaned_data
        if du_lieu['q']:
            danh_sach = danh_sach.filter(
                Q(ma_ho_so__icontains=du_lieu['q'])
                | Q(ho_va_ten__icontains=du_lieu['q'])
                | Q(nguoi_dung__username__icontains=du_lieu['q'])
            )
        if du_lieu['department']:
            danh_sach = danh_sach.filter(phong_ban=du_lieu['department'])
        if du_lieu['position']:
            danh_sach = danh_sach.filter(chuc_vu=du_lieu['position'])
        if du_lieu['status']:
            danh_sach = danh_sach.filter(trang_thai_nv=du_lieu['status'])
        if du_lieu['hire_from']:
            danh_sach = danh_sach.filter(ngay_vao_lam__gte=du_lieu['hire_from'])
        if du_lieu['hire_to']:
            danh_sach = danh_sach.filter(ngay_vao_lam__lte=du_lieu['hire_to'])
        return danh_sach


NguoiDung = get_user_model()


class BieuMauThietLapLuong(forms.Form):
    ma_so_bhxh = forms.CharField(label='Mã số BHXH', required=False, max_length=30)
    ma_so_thue = forms.CharField(label='Mã số thuế', required=False, max_length=30)
    ten_ngan_hang = forms.CharField(label='Tên ngân hàng', required=False, max_length=150)
    so_tai_khoan = forms.CharField(label='Số tài khoản', required=False, max_length=50)
    luong_dong_bao_hiem = forms.DecimalField(label='Lương đóng bảo hiểm (VNĐ)', min_value=0, max_digits=16, decimal_places=2)
    ty_le_bhxh = forms.DecimalField(label='BHXH nhân viên đóng (%)', min_value=0, max_value=100, initial=8)
    ty_le_bhyt = forms.DecimalField(label='BHYT nhân viên đóng (%)', min_value=0, max_value=100, initial=Decimal('1.5'))
    ty_le_bhtn = forms.DecimalField(label='BHTN nhân viên đóng (%)', min_value=0, max_value=100, initial=1)
    can_cu_bao_hiem = forms.CharField(label='Căn cứ bảo hiểm', widget=forms.Textarea(attrs={'rows': 2}))
    doi_tuong_tinh_thue = forms.ChoiceField(label='Đối tượng tính thuế', choices=[('resident_2026', 'Cá nhân cư trú, hợp đồng từ 03 tháng'), ('other', 'Trường hợp khác/chưa xác định')])
    giam_tru_ban_than = forms.BooleanField(label='Giảm trừ bản thân tại TVT', required=False)
    can_cu_thue = forms.CharField(label='Căn cứ thuế và giảm trừ', widget=forms.Textarea(attrs={'rows': 2}))
    phu_cap_an_trua = forms.DecimalField(label='Phụ cấp ăn trưa (VNĐ/tháng)', min_value=0, max_digits=16, decimal_places=2, initial=450000)
    luong_gio_tang_ca = forms.DecimalField(label='Lương giờ căn cứ OT (VNĐ)', required=False, min_value=Decimal('.0001'), max_digits=18, decimal_places=4)
    can_cu_luong_gio_tang_ca = forms.CharField(label='Căn cứ lương giờ OT', required=False, widget=forms.Textarea(attrs={'rows': 2}))

    so_nguoi_phu_thuoc = forms.IntegerField(label='Số người phụ thuộc', min_value=0, initial=0, required=False)

    KHOA_CAU_HINH = {
        'so_nguoi_phu_thuoc': 'so_nguoi_phu_thuoc',
        'ma_so_bhxh': 'ma_so_bhxh',
        'ma_so_thue': 'ma_so_thue',
        'ten_ngan_hang': 'ten_ngan_hang',
        'so_tai_khoan': 'so_tai_khoan',
        'luong_dong_bao_hiem': 'luong_dong_bao_hiem',
        'can_cu_bao_hiem': 'can_cu_bao_hiem',
        'doi_tuong_tinh_thue': 'doi_tuong_tinh_thue',
        'giam_tru_ban_than': 'giam_tru_ban_than',
        'can_cu_thue': 'can_cu_thue',
        'phu_cap_an_trua': 'phu_cap_an_trua',
        'luong_gio_tang_ca': 'luong_gio_tang_ca',
        'can_cu_luong_gio_tang_ca': 'can_cu_luong_gio_tang_ca',
    }
    KHOA_TY_LE = {'ty_le_bhxh': 'BHXH', 'ty_le_bhyt': 'BHYT', 'ty_le_bhtn': 'BHTN'}

    def __init__(self, ho_so=None, data=None):
        thiet_lap = ho_so.thiet_lap_luong if ho_so else None
        gia_tri_mac_dinh = dict(thiet_lap or {})
        cac_ty_le = gia_tri_mac_dinh.pop('ty_le_bao_hiem', {})
        for ten_truong, ma_bao_hiem in self.KHOA_TY_LE.items():
            if cac_ty_le:
                gia_tri_mac_dinh[ten_truong] = Decimal(str(cac_ty_le.get(ma_bao_hiem, 0))) * 100
        super().__init__(data, initial=gia_tri_mac_dinh, prefix='salary')

    def clean(self):
        du_lieu = super().clean()
        if sum((du_lieu.get(ten_truong, 0) for ten_truong in self.KHOA_TY_LE)) > 100:
            raise forms.ValidationError('Tổng tỷ lệ bảo hiểm không vượt quá 100%.')
        if du_lieu.get('luong_gio_tang_ca') and not du_lieu.get('can_cu_luong_gio_tang_ca'):
            self.add_error('can_cu_luong_gio_tang_ca', 'Cần ghi căn cứ lương giờ OT.')
        return du_lieu

    def du_lieu_thiet_lap(self):
        from bang_luong.services.can_cu_luong_service import chuan_hoa_du_lieu
        du_lieu = dict(self.cleaned_data)
        du_lieu['ty_le_bao_hiem'] = {
            ma_bao_hiem: format((du_lieu.pop(ten_truong) / 100).normalize(), 'f')
            for ten_truong, ma_bao_hiem in self.KHOA_TY_LE.items()
        }
        du_lieu['so_nguoi_phu_thuoc'] = du_lieu['so_nguoi_phu_thuoc'] or 0
        return chuan_hoa_du_lieu(du_lieu)


class BieuMauNhanVien(forms.ModelForm):
    ten_dang_nhap = forms.CharField(label='Tên đăng nhập', max_length=150)
    email = forms.EmailField(label='Email')
    trang_thai_tai_khoan = forms.BooleanField(label='Tài khoản đang hoạt động', required=False, initial=True)
    mat_khau = forms.CharField(label='Mật khẩu', min_length=8, widget=forms.PasswordInput, required=False)
    xac_nhan_mat_khau = forms.CharField(label='Xác nhận mật khẩu', widget=forms.PasswordInput, required=False)

    class Meta:
        model = NhanVien
        fields = ('hinh_anh', 'ho_va_ten', 'ma_ho_so', 'ngay_sinh', 'gioi_tinh', 'cccd', 'so_dien_thoai',
                  'dia_chi', 'trang_thai_nv', 'phong_ban', 'chuc_vu', 'ngay_vao_lam', 'luong_co_ban')
        widgets = {
            'ngay_sinh': forms.DateInput(attrs={'type': 'date'}),
            'ngay_vao_lam': forms.DateInput(attrs={'type': 'date'}),
            'luong_co_ban': forms.NumberInput(attrs={'min': '0', 'step': '1'}),
        }

    def __init__(self, *args, **kwargs):
        self.ho_so_dang_sua = kwargs.get('instance')
        super().__init__(*args, **kwargs)
        self.fields['hinh_anh'].required = False
        for ten_truong in ('ho_va_ten', 'ma_ho_so', 'ngay_sinh', 'gioi_tinh', 'cccd', 'so_dien_thoai',
                           'phong_ban', 'chuc_vu', 'ngay_vao_lam', 'luong_co_ban'):
            self.fields[ten_truong].required = True
        self.fields['chuc_vu'].queryset = self.fields['chuc_vu'].queryset.select_related('phong_ban')
        if self.ho_so_dang_sua:
            for ten_truong in ('mat_khau', 'xac_nhan_mat_khau'):
                self.fields.pop(ten_truong, None)
            self.fields['hinh_anh'].widget = forms.FileInput(
                attrs={'accept': '.jpg,.jpeg,.png,.webp', 'class': 'hinh_anh-input-hidden'})
            nguoi_dung = self.ho_so_dang_sua.nguoi_dung
            self.fields['ten_dang_nhap'].initial = nguoi_dung.username
            self.fields['email'].initial = nguoi_dung.email
            self.fields['trang_thai_tai_khoan'].initial = nguoi_dung.is_active
        else:
            self.fields['mat_khau'].required = True
            self.fields['xac_nhan_mat_khau'].required = True

    def clean_email(self):
        email = self.cleaned_data['email']
        tai_khoan_trung = NguoiDung.objects.filter(email__iexact=email)
        if self.ho_so_dang_sua:
            tai_khoan_trung = tai_khoan_trung.exclude(pk=self.ho_so_dang_sua.nguoi_dung_id)
        if tai_khoan_trung.exists():
            raise ValidationError('Email đã được sử dụng.')
        return email

    def clean_ten_dang_nhap(self):
        ten_dang_nhap = self.cleaned_data['ten_dang_nhap']
        tai_khoan_trung = NguoiDung.objects.filter(username__iexact=ten_dang_nhap)
        if self.ho_so_dang_sua:
            tai_khoan_trung = tai_khoan_trung.exclude(pk=self.ho_so_dang_sua.nguoi_dung_id)
        if tai_khoan_trung.exists():
            raise ValidationError('Tên đăng nhập đã được sử dụng.')
        return ten_dang_nhap

    def clean(self):
        du_lieu_sach = super().clean()
        mat_khau = du_lieu_sach.get('mat_khau')
        xac_nhan_mat_khau = du_lieu_sach.get('xac_nhan_mat_khau')
        if mat_khau and mat_khau != xac_nhan_mat_khau:
            self.add_error('xac_nhan_mat_khau', 'Mật khẩu xác nhận không khớp.')
        if mat_khau:
            try:
                validate_password(mat_khau, self.ho_so_dang_sua.nguoi_dung if self.ho_so_dang_sua else None)
            except ValidationError as loi:
                self.add_error('mat_khau', loi)
        if du_lieu_sach.get('cccd') and (len(du_lieu_sach['cccd']) != 12 or not du_lieu_sach['cccd'].isdigit()):
            self.add_error('cccd', 'CCCD phải gồm đúng 12 chữ số.')
        chuc_vu = du_lieu_sach.get('chuc_vu')
        if chuc_vu and du_lieu_sach.get('phong_ban') and chuc_vu.phong_ban_id != du_lieu_sach['phong_ban'].id:
            self.add_error('chuc_vu', 'Chức vụ phải thuộc phòng ban đã chọn.')
        return du_lieu_sach

    @transaction.atomic
    def save(self, commit=True):
        ho_so = super().save(commit=False)
        ho_so.dang_hoat_dong = ho_so.trang_thai_nv == 'Đang làm việc'
        if self.ho_so_dang_sua:
            nguoi_dung = self.ho_so_dang_sua.nguoi_dung
        else:
            nguoi_dung = NguoiDung(username=self.cleaned_data['ten_dang_nhap'])
        nguoi_dung.username = self.cleaned_data['ten_dang_nhap']
        nguoi_dung.email = self.cleaned_data['email']
        nguoi_dung.is_active = self.cleaned_data['trang_thai_tai_khoan']
        if self.cleaned_data.get('mat_khau'):
            nguoi_dung.set_password(self.cleaned_data['mat_khau'])
        nguoi_dung.save()
        ho_so.nguoi_dung = nguoi_dung
        if commit:
            ho_so.save()
            self.save_m2m()
        return ho_so


class BieuMauHoSoCaNhan(forms.ModelForm):
    email = forms.EmailField(label='Email', required=False)

    class Meta:
        model = NhanVien
        fields = ('hinh_anh', 'ho_va_ten', 'ngay_sinh', 'gioi_tinh', 'cccd', 'so_dien_thoai', 'dia_chi')
        widgets = {'ngay_sinh': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].initial = self.instance.nguoi_dung.email
        self.fields['hinh_anh'].required = False
        self.fields['hinh_anh'].widget = forms.FileInput(
            attrs={'accept': '.jpg,.jpeg,.png,.webp', 'class': 'hinh_anh-input-hidden'})

    def clean_email(self):
        email = self.cleaned_data['email']
        if email and NguoiDung.objects.filter(email__iexact=email).exclude(pk=self.instance.nguoi_dung_id).exists():
            raise ValidationError('Email đã được sử dụng.')
        return email

    def clean_cccd(self):
        cccd = self.cleaned_data.get('cccd')
        if cccd and (len(cccd) != 12 or not cccd.isdigit()):
            raise ValidationError('CCCD phải gồm đúng 12 chữ số.')
        return cccd

    @transaction.atomic
    def save(self, commit=True):
        nhan_vien = super().save(commit=commit)
        self.instance.nguoi_dung.email = self.cleaned_data['email']
        self.instance.nguoi_dung.save(update_fields=['email'])
        return nhan_vien


class BieuMauHocVan(forms.ModelForm):
    xoa_tep_bang_cap = forms.BooleanField(required=False, label='Xóa tệp hiện tại')

    class Meta:
        model = HocVan
        fields = ('ma_hoc_van', 'bang_cap', 'chuyen_nganh', 'truong_hoc', 'nam_tot_nghiep', 'tep_bang_cap')
        widgets = {'nam_tot_nghiep': forms.NumberInput(attrs={'min': '1900', 'max': '2100'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tep_bang_cap'].widget = forms.FileInput(
            attrs={'accept': '.pdf,.doc,.docx,.jpg,.jpeg,.png', 'class': 'education-file-input',
                   'data-file-replacement': 'true'})

    def clean(self):
        du_lieu_sach = super().clean()
        if du_lieu_sach.get('xoa_tep_bang_cap') and not self.files.get('tep_bang_cap'):
            du_lieu_sach['tep_bang_cap'] = False
        return du_lieu_sach


class BieuMauHopDong(forms.ModelForm):
    xoa_tep_hop_dong = forms.BooleanField(required=False, label='Xóa tệp hiện tại')

    class Meta:
        model = HopDongLaoDong
        fields = ('ma_hop_dong', 'so_hop_dong', 'loai_hop_dong', 'ngay_ky', 'ngay_bat_dau', 'ngay_ket_thuc',
                  'luong_thoa_thuan', 'trang_thai', 'tep_hop_dong')
        widgets = {
            'ngay_ky': forms.DateInput(attrs={'type': 'date'}),
            'ngay_bat_dau': forms.DateInput(attrs={'type': 'date'}),
            'ngay_ket_thuc': forms.DateInput(attrs={'type': 'date'}),
            'luong_thoa_thuan': forms.NumberInput(attrs={'min': '0', 'step': '1'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tep_hop_dong'].widget = forms.FileInput(
            attrs={'accept': '.pdf,.doc,.docx,.jpg,.jpeg,.png', 'class': 'education-file-input',
                   'data-file-replacement': 'true'})

    def clean(self):
        du_lieu_sach = super().clean()
        if du_lieu_sach.get('xoa_tep_hop_dong') and not self.files.get('tep_hop_dong'):
            du_lieu_sach['tep_hop_dong'] = False
        ngay_bat_dau = du_lieu_sach.get('ngay_bat_dau')
        ngay_ket_thuc = du_lieu_sach.get('ngay_ket_thuc')
        if ngay_bat_dau and ngay_ket_thuc and ngay_ket_thuc < ngay_bat_dau:
            self.add_error('ngay_ket_thuc', 'Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.')
        return du_lieu_sach
