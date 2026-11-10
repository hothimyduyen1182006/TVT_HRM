from django import forms
from employees.access import visible_employees
from .models import PayrollInput, PayrollAdjustment, PayrollPeriod
from employees.filters import PeriodFilter
from django.utils import timezone
from decimal import Decimal
from django.forms import BaseFormSet, formset_factory


class InsuranceRateForm(forms.Form):
    name = forms.CharField(label='Loại bảo hiểm', max_length=80,
        widget=forms.TextInput(attrs={'placeholder': 'Ví dụ: BHXH'}))
    percent = forms.DecimalField(label='Tỷ lệ người lao động đóng (%)', min_value=0, max_value=100,
        max_digits=7, decimal_places=4, widget=forms.NumberInput(attrs={'step': '0.0001', 'placeholder': '%'}))


class BaseInsuranceRateFormSet(BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        names, total = set(), Decimal(0)
        for form in self.forms:
            data = form.cleaned_data
            if not data or data.get('DELETE'):
                continue
            name = data['name'].strip().casefold()
            if name in names:
                raise forms.ValidationError('Mỗi loại bảo hiểm chỉ được nhập một lần.')
            names.add(name)
            total += data['percent']
        if total > 100:
            raise forms.ValidationError('Tổng tỷ lệ bảo hiểm không được vượt 100%.')


InsuranceRateFormSet = formset_factory(InsuranceRateForm, formset=BaseInsuranceRateFormSet,
                                     extra=1, can_delete=True, max_num=20, validate_max=True)


class PayrollFilter(PeriodFilter):
    q = forms.CharField(label='Từ khóa (Họ tên / ID)', required=False, max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Tìm theo họ tên hoặc ID...'}))
    status = forms.ChoiceField(label='Trạng thái', required=False,
        choices=[('', 'Tất cả'), *PayrollPeriod._meta.get_field('status').choices])

    def __init__(self, user, data=None):
        super().__init__(user, data)
        self.fields['department'].empty_label = 'Tất cả'
        set_period_widgets(self)


def set_period_widgets(form):
    form.fields['month'].widget = forms.Select(choices=[(month, f'Tháng {month:02}') for month in range(1, 13)])
    form.fields['year'].widget = forms.Select(choices=[(year, f'Năm {year}') for year in range(2000, 2101)])


class PayslipFilter(forms.Form):
    month = forms.IntegerField(label='Tháng', min_value=1, max_value=12)
    year = forms.IntegerField(label='Năm', min_value=2000, max_value=2100)

    def __init__(self, data=None):
        today = timezone.localdate()
        values = {'month': today.month, 'year': today.year}
        if data:
            values.update(data.dict() if hasattr(data, 'dict') else data)
        super().__init__(values)
        set_period_widgets(self)

    def clean(self):
        data = super().clean()
        # Phiếu cá nhân không nhận bộ lọc có thể mở rộng sang người khác.
        if any(self.data.get(key) for key in ['employee', 'department', 'q', 'status']):
            raise forms.ValidationError('Phiếu cá nhân chỉ cho phép chọn tháng và năm.')
        return data


class PayrollInputFilter(PayrollFilter):
    readiness = forms.ChoiceField(label='Tình trạng dữ liệu', required=False, choices=[
        ('', 'Tất cả'), ('missing', 'Chưa nhập'), ('draft', 'Chưa kiểm tra'),
        ('verified', 'Đã kiểm tra'), ('locked', 'Đã khóa')])

    def __init__(self, user, data=None):
        super().__init__(user, data)
        self.fields.pop('status')


class ScopedInputForm(forms.ModelForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee'].queryset = visible_employees(user)
        self.fields['period'].queryset = PayrollPeriod.objects.filter(status='pending')
        self.fields['period'].label = 'Kỳ lương'
        self.fields['employee'].label = 'Nhân viên'
        self.fields['period'].label_from_instance = lambda item: f'Tháng {item.attendance_period}'
        if self.instance.pk:
            self.fields['employee'].disabled = True
            self.fields['period'].disabled = True
        else:
            if self.initial.get('employee'):
                self.fields['employee'].disabled = True
            if self.initial.get('period'):
                self.fields['period'].disabled = True


class PayrollInputForm(ScopedInputForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        initial_rates = [{'name': key, 'percent': (Decimal(str(rate)) * 100).normalize()}
                         for key, rate in self.instance.insurance_rates.items()]
        self.legacy_rates = self.is_bound and 'insurance_rates' in self.data and 'insurance-TOTAL_FORMS' not in self.data
        self.rate_formset = InsuranceRateFormSet(self.data if self.is_bound and not self.legacy_rates else None,
                                               initial=initial_rates, prefix='insurance')
        self.fields['insurance_base'].label = 'Lương làm căn cứ đóng bảo hiểm (VNĐ)'
        self.fields['tax_amount'].label = 'Thuế TNCN đã xác định trong kỳ (VNĐ)'
        self.fields['verified'].label = 'Tôi đã kiểm tra dữ liệu và căn cứ áp dụng trong kỳ'
        self.fields['insurance_basis'].widget = forms.Textarea(attrs={'rows': 3})
        self.fields['tax_basis'].widget = forms.Textarea(attrs={'rows': 3})
        self.fields['overtime_basis'].widget = forms.Textarea(attrs={'rows':3})
        self.fields['overtime_hourly_rate'].help_text='Bắt buộc khi có OT tự động từ chấm công. HR xác định lương giờ thực trả hợp lệ; không bao gồm thưởng, tiền ăn và khoản không thuộc căn cứ OT.'
        self.fields['insurance_basis'].help_text = 'Ghi đối tượng, kỳ và chính sách áp dụng; nếu không tham gia phải ghi rõ căn cứ.'
        self.fields['tax_basis'].help_text = 'Ghi căn cứ số thuế, kể cả trường hợp không phát sinh. Hệ thống không tự áp dụng biểu thuế.'

    def clean(self):
        data = super().clean()
        if self.legacy_rates:
            self.instance.insurance_rates = forms.JSONField().clean(self.data['insurance_rates'])
        elif not self.rate_formset.is_valid():
            raise forms.ValidationError('Vui lòng kiểm tra bảng tỷ lệ bảo hiểm.')
        else:
            self.instance.insurance_rates = {
                form.cleaned_data['name'].strip(): format((form.cleaned_data['percent'] / 100).normalize(), 'f')
                for form in self.rate_formset if form.cleaned_data and not form.cleaned_data.get('DELETE')}
        return data

    class Meta:
        model = PayrollInput
        fields = ['period', 'employee', 'insurance_base', 'insurance_basis',
                  'tax_amount', 'tax_basis', 'overtime_hourly_rate', 'overtime_basis', 'verified']


class AdjustmentForm(ScopedInputForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.fields['amount'].label = 'Số tiền (VNĐ)'
        self.fields['approved'].label = 'Khoản này đã được duyệt theo thẩm quyền'
        self.fields['basis'].widget = forms.Textarea(attrs={'rows': 3})
        self.fields['basis'].help_text = 'Ghi căn cứ khoản tiền. Không trừ thêm tiền cho thời gian đi muộn đã giảm công.'

    class Meta:
        model = PayrollAdjustment
        fields = ['period', 'employee', 'name', 'kind', 'amount', 'basis', 'approved']
