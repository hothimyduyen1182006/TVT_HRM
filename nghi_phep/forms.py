from django import forms
from django.core.exceptions import ValidationError
from .models import LeaveRequest

MAX_EVIDENCE_SIZE = 5 * 1024 * 1024
EVIDENCE_CONTENT_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif', 'application/pdf'}
EVIDENCE_ACCEPT = '.jpg,.jpeg,.png,.webp,.gif,.pdf,image/jpeg,image/png,image/webp,image/gif,application/pdf'


class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ['Ngay_bat_dau', 'Ngay_ket_thuc', 'leave_type', 'Ly_do', 'Tep_dinh_kem']
        widgets = {
            'Ngay_bat_dau': forms.DateInput(attrs={'type': 'date', 'class': 'leave-input'}),
            'Ngay_ket_thuc': forms.DateInput(attrs={'type': 'date', 'class': 'leave-input'}),
            'leave_type': forms.Select(attrs={'class': 'leave-input'}),
            'Ly_do': forms.Textarea(attrs={
                'class': 'leave-input',
                'rows': 3,
                'placeholder': 'Nhập lý do xin nghỉ phép',
            }),
            'Tep_dinh_kem': forms.ClearableFileInput(attrs={'accept': EVIDENCE_ACCEPT, 'class': 'leave-file-input'}),
        }

    def clean_Tep_dinh_kem(self):
        return validate_evidence(self.cleaned_data.get('Tep_dinh_kem'))


class LeaveEvidenceForm(forms.Form):
    evidence = forms.FileField(label='Ảnh minh chứng', widget=forms.ClearableFileInput(
        attrs={'accept': EVIDENCE_ACCEPT}))

    def clean_evidence(self):
        return validate_evidence(self.cleaned_data.get('evidence'))


def validate_evidence(uploaded_file):
    if not uploaded_file:
        return uploaded_file
    if uploaded_file.size > MAX_EVIDENCE_SIZE:
        raise ValidationError('Tệp minh chứng không được vượt quá 5 MB.')
    if uploaded_file.content_type not in EVIDENCE_CONTENT_TYPES:
        raise ValidationError('Vui lòng tải lên ảnh JPG, PNG, WEBP, GIF hoặc tệp PDF.')
    return uploaded_file


class LeaveFilterForm(forms.Form):
    q = forms.CharField(required=False, label='Từ khóa')
    department = forms.IntegerField(required=False, widget=forms.Select(), label='Phòng ban')
    status = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'Tất cả trạng thái'),
            ('pending', 'Đang chờ'),
            ('approved', 'Đã duyệt'),
            ('rejected', 'Từ chối'),
        ],
        label='Trạng thái',
    )
    leave_type = forms.ChoiceField(
        required=False,
        choices=[('', 'Tất cả loại nghỉ'), *LeaveRequest.LEAVE_TYPES],
        label='Loại nghỉ',
    )
    start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}), label='Từ ngày')
    end_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}), label='Đến ngày')

    def __init__(self, departments, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].widget = forms.Select(choices=[('', 'Tất cả phòng ban'),
            *[(d.pk, d.name) for d in departments]])

