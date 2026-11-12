from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from decimal import Decimal

from .models import Education, Employee, LaborContract


class DashboardEmployeeFilter(forms.Form):
    active_as_of = forms.DateField(label='Nhân viên đang hoạt động đến ngày', required=False,
                                   widget=forms.DateInput(attrs={'type': 'date'}))
    gender = forms.ChoiceField(label='Giới tính', required=False,
        choices=[('', 'Tất cả'), ('Nam', 'Nam'), ('Nữ', 'Nữ'), ('unknown', 'Chưa cập nhật')])


User = get_user_model()


class SalarySettingsForm(forms.Form):
    insurance_number = forms.CharField(label='Mã số BHXH', required=False, max_length=30)
    tax_code = forms.CharField(label='Mã số thuế', required=False, max_length=30)
    bank_name = forms.CharField(label='Tên ngân hàng', required=False, max_length=150)
    bank_account = forms.CharField(label='Số tài khoản', required=False, max_length=50)
    insurance_base = forms.DecimalField(label='Lương đóng bảo hiểm (VNĐ)',min_value=0,max_digits=16,decimal_places=2)
    bhxh = forms.DecimalField(label='BHXH nhân viên đóng (%)',min_value=0,max_value=100,initial=8)
    bhyt = forms.DecimalField(label='BHYT nhân viên đóng (%)',min_value=0,max_value=100,initial=Decimal('1.5'))
    bhtn = forms.DecimalField(label='BHTN nhân viên đóng (%)',min_value=0,max_value=100,initial=1)
    insurance_basis = forms.CharField(label='Căn cứ bảo hiểm',widget=forms.Textarea(attrs={'rows':2}))
    tax_method = forms.ChoiceField(label='Đối tượng tính thuế',choices=[('resident_2026','Cá nhân cư trú, hợp đồng từ 03 tháng'),('other','Trường hợp khác/chưa xác định')])
    claim_personal_deduction = forms.BooleanField(label='Giảm trừ bản thân tại TVT',required=False)
    tax_basis = forms.CharField(label='Căn cứ thuế và giảm trừ',widget=forms.Textarea(attrs={'rows':2}))
    lunch_allowance = forms.DecimalField(label='Phụ cấp ăn trưa (VNĐ/tháng)',min_value=0,max_digits=16,decimal_places=2,initial=450000)
    overtime_hourly_rate = forms.DecimalField(label='Lương giờ căn cứ OT (VNĐ)',required=False,min_value=Decimal('.0001'),max_digits=18,decimal_places=4)
    overtime_basis = forms.CharField(label='Căn cứ lương giờ OT',required=False,widget=forms.Textarea(attrs={'rows':2}))
    verified = forms.BooleanField(label='Đã kiểm tra căn cứ tính lương',required=False)

    def __init__(self, employee=None, data=None):
        settings = employee.payroll_settings if employee else None
        initial = dict(settings or {})
        rates=initial.pop('insurance_rates',{})
        for name in ['bhxh','bhyt','bhtn']:
            if rates: initial[name]=Decimal(str(rates.get(name.upper(),0)))*100
        super().__init__(data,initial=initial,prefix='salary')

    def clean(self):
        data=super().clean()
        if sum((data.get(key,0) for key in ['bhxh','bhyt','bhtn']))>100:
            raise forms.ValidationError('Tổng tỷ lệ bảo hiểm không vượt quá 100%.')
        if data.get('overtime_hourly_rate') and not data.get('overtime_basis'):
            self.add_error('overtime_basis','Cần ghi căn cứ lương giờ OT.')
        return data

    def settings_data(self):
        from payroll.services.source_data import canonical
        data=dict(self.cleaned_data)
        data['insurance_rates']={key.upper():format((data.pop(key)/100).normalize(),'f') for key in ['bhxh','bhyt','bhtn']}
        data['tax_dependents']=0
        return canonical(data)


class EmployeeForm(forms.ModelForm):
    username = forms.CharField(label='Tên đăng nhập', max_length=150)
    email = forms.EmailField(label='Email')
    account_active = forms.BooleanField(label='Tài khoản đang hoạt động', required=False, initial=True)
    password = forms.CharField(label='Mật khẩu', min_length=8, widget=forms.PasswordInput, required=False)
    password_confirm = forms.CharField(label='Xác nhận mật khẩu', widget=forms.PasswordInput, required=False)

    class Meta:
        model = Employee
        fields = ('avatar', 'full_name', 'code', 'date_of_birth', 'gender', 'national_id', 'phone',
                  'address', 'employment_status', 'department', 'position', 'hire_date', 'base_salary')
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'hire_date': forms.DateInput(attrs={'type': 'date'}),
            'base_salary': forms.NumberInput(attrs={'min': '0', 'step': '1'}),
        }

    def __init__(self, *args, **kwargs):
        self.employee_instance = kwargs.get('instance')
        super().__init__(*args, **kwargs)
        self.fields['avatar'].required = False
        for field in ('full_name', 'code', 'date_of_birth', 'gender', 'national_id', 'phone',
                      'department', 'position', 'hire_date', 'base_salary'):
            self.fields[field].required = True
        self.fields['position'].queryset = self.fields['position'].queryset.select_related('department')
        if self.employee_instance:
            for name in ('password', 'password_confirm'):
                self.fields.pop(name, None)
            self.fields['avatar'].widget = forms.FileInput(
                attrs={'accept': '.jpg,.jpeg,.png,.webp', 'class': 'avatar-input-hidden'})
            user = self.employee_instance.user
            self.fields['username'].initial = user.username
            self.fields['email'].initial = user.email
            self.fields['account_active'].initial = user.is_active
        else:
            self.fields['password'].required = True
            self.fields['password_confirm'].required = True

    def clean_email(self):
        email = self.cleaned_data['email']
        users = User.objects.filter(email__iexact=email)
        if self.employee_instance:
            users = users.exclude(pk=self.employee_instance.user_id)
        if users.exists():
            raise ValidationError('Email đã được sử dụng.')
        return email

    def clean_username(self):
        username = self.cleaned_data['username']
        users = User.objects.filter(username__iexact=username)
        if self.employee_instance:
            users = users.exclude(pk=self.employee_instance.user_id)
        if users.exists():
            raise ValidationError('Tên đăng nhập đã được sử dụng.')
        return username

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password')
        confirmation = cleaned.get('password_confirm')
        if password and password != confirmation:
            self.add_error('password_confirm', 'Mật khẩu xác nhận không khớp.')
        if password:
            try:
                validate_password(password, self.employee_instance.user if self.employee_instance else None)
            except ValidationError as error:
                self.add_error('password', error)
        if cleaned.get('national_id') and (len(cleaned['national_id']) != 12 or not cleaned['national_id'].isdigit()):
            self.add_error('national_id', 'CCCD phải gồm đúng 12 chữ số.')
        position = cleaned.get('position')
        if position and cleaned.get('department') and position.department_id != cleaned['department'].id:
            self.add_error('position', 'Chức vụ phải thuộc phòng ban đã chọn.')
        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        employee = super().save(commit=False)
        employee.is_active = employee.employment_status == 'Đang làm việc'
        if self.employee_instance:
            user = self.employee_instance.user
        else:
            user = User(username=self.cleaned_data['username'])
        user.username = self.cleaned_data['username']
        user.email = self.cleaned_data['email']
        user.is_active = self.cleaned_data['account_active']
        if self.cleaned_data.get('password'):
            user.set_password(self.cleaned_data['password'])
        user.save()
        employee.user = user
        if commit:
            employee.save()
            self.save_m2m()
        return employee


class PersonalProfileForm(forms.ModelForm):
    email = forms.EmailField(label='Email', required=False)

    class Meta:
        model = Employee
        fields = ('avatar', 'full_name', 'date_of_birth', 'gender', 'national_id', 'phone', 'address')
        widgets = {'date_of_birth': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].initial = self.instance.user.email
        self.fields['avatar'].required = False
        self.fields['avatar'].widget = forms.FileInput(
            attrs={'accept': '.jpg,.jpeg,.png,.webp', 'class': 'avatar-input-hidden'})

    def clean_email(self):
        email = self.cleaned_data['email']
        if email and User.objects.filter(email__iexact=email).exclude(pk=self.instance.user_id).exists():
            raise ValidationError('Email đã được sử dụng.')
        return email

    def clean_national_id(self):
        national_id = self.cleaned_data.get('national_id')
        if national_id and (len(national_id) != 12 or not national_id.isdigit()):
            raise ValidationError('CCCD phải gồm đúng 12 chữ số.')
        return national_id

    @transaction.atomic
    def save(self, commit=True):
        employee = super().save(commit=commit)
        self.instance.user.email = self.cleaned_data['email']
        self.instance.user.save(update_fields=['email'])
        return employee


class EducationForm(forms.ModelForm):
    remove_certificate = forms.BooleanField(required=False, label='Xóa tệp hiện tại')

    class Meta:
        model = Education
        fields = ('code', 'degree', 'major', 'school', 'graduation_year', 'certificate_file')
        widgets = {'graduation_year': forms.NumberInput(attrs={'min': '1900', 'max': '2100'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['certificate_file'].widget = forms.FileInput(
            attrs={'accept': '.pdf,.doc,.docx,.jpg,.jpeg,.png', 'class': 'education-file-input',
                   'data-file-replacement': 'true'})

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('remove_certificate') and not self.files.get('certificate_file'):
            cleaned['certificate_file'] = False
        return cleaned


class LaborContractForm(forms.ModelForm):
    remove_contract_file = forms.BooleanField(required=False, label='Xóa tệp hiện tại')

    class Meta:
        model = LaborContract
        fields = ('code', 'number', 'contract_type', 'signed_date', 'start_date', 'end_date',
                  'agreed_salary', 'status', 'contract_file')
        widgets = {
            'signed_date': forms.DateInput(attrs={'type': 'date'}),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'agreed_salary': forms.NumberInput(attrs={'min': '0', 'step': '1'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['contract_file'].widget = forms.FileInput(
            attrs={'accept': '.pdf,.doc,.docx,.jpg,.jpeg,.png', 'class': 'education-file-input',
                   'data-file-replacement': 'true'})

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('remove_contract_file') and not self.files.get('contract_file'):
            cleaned['contract_file'] = False
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', 'Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.')
        return cleaned
