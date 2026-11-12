from django import forms
from django.utils import timezone

from .access import visible_employees
from .models import Department, Employee


class PeriodFilter(forms.Form):
    month = forms.IntegerField(label='Tháng', min_value=1, max_value=12)
    year = forms.IntegerField(label='Năm', min_value=2000, max_value=2100)
    employee = forms.ModelChoiceField(label='Nhân viên', queryset=Employee.objects.none(), required=False)
    department = forms.ModelChoiceField(label='Phòng ban', queryset=Department.objects.none(), required=False)

    def __init__(self, user, data=None):
        today = timezone.localdate()
        values = {'month': today.month, 'year': today.year}
        if data:
            values.update(data.dict())
        super().__init__(values)
        employees = visible_employees(user)
        self.fields['employee'].queryset = employees
        self.fields['department'].queryset = Department.objects.filter(
            pk__in=employees.values('department_id')
        )

    def employee_scope(self, user):
        scope = visible_employees(user)
        if self.cleaned_data.get('employee'):
            scope = scope.filter(pk=self.cleaned_data['employee'].pk)
        if self.cleaned_data.get('department'):
            scope = scope.filter(department=self.cleaned_data['department'])
        return scope
