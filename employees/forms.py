from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from .models import Education, Employee, LaborContract


User = get_user_model()


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
            user = self.employee_instance.user
            self.fields['username'].initial = user.username
            self.fields['email'].initial = user.email
            self.fields['account_active'].initial = user.is_active
            self.fields['password'].help_text = 'Để trống nếu không đổi mật khẩu.'
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


class EducationForm(forms.ModelForm):
    class Meta:
        model = Education
        fields = ('code', 'degree', 'major', 'school', 'graduation_year', 'certificate_file')
        widgets = {'graduation_year': forms.NumberInput(attrs={'min': '1900', 'max': '2100'})}


class LaborContractForm(forms.ModelForm):
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

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', 'Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.')
        return cleaned
