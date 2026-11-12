from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms.models import model_to_dict
from employees.access import require_role, HR, DIRECTOR
from payroll.models import PayrollPeriod, PayrollAuditLog
from attendance.models import AttendancePeriod
from .source_data import canonical


def employee_input(employee, period):
    """Lấy bộ thiết lập chung; đầu vào theo kỳ chỉ giữ tương thích dữ liệu cũ."""
    from payroll.models import PayrollInput
    existing=PayrollInput.objects.filter(employee=employee,period=period).first()
    settings=employee.payroll_settings
    if settings is None:
        if not existing or not existing.verified:
            raise ValidationError(f'{employee}: thiếu dữ liệu thuế/BH đã kiểm tra.')
        return existing
    if not settings.get('verified'):
        raise ValidationError(f'{employee}: thiết lập tính lương chưa được kiểm tra.')
    from copy import copy
    value=copy(existing) if existing else PayrollInput(employee=employee,period=period)
    for key in ['insurance_base','insurance_rates','insurance_basis','tax_method','tax_basis',
                'claim_personal_deduction','overtime_hourly_rate','overtime_basis','verified']:
        setattr(value,key,settings.get(key))
    for key in ['insurance_base','overtime_hourly_rate']:
        if getattr(value,key) is not None: setattr(value,key,Decimal(str(getattr(value,key))))
    value.tax_dependents=0
    value.shared_settings=settings
    return value


def employee_adjustments(employee, period):
    from payroll.models import PayrollAdjustment
    if employee.payroll_settings is None:
        return PayrollAdjustment.objects.filter(employee=employee,period=period,approved=True)
    from types import SimpleNamespace
    from django.db.models import Q
    historical=list(PayrollAdjustment.objects.filter(employee=employee,period=period,approved=True).exclude(
        Q(tax_category='meal_cash') | Q(name__in=['Phụ cấp ăn trưa','Ăn trưa'])).order_by('pk'))
    return historical+[SimpleNamespace(pk=f'employee-{employee.pk}-lunch',name='Phụ cấp ăn trưa',kind='allowance',
        amount=Decimal(str(employee.payroll_settings.get('lunch_allowance',450000))),tax_category='meal_cash',
        basis='Phụ cấp ăn trưa dùng chung đã được xác nhận trong quản lý nhân viên')]


def record_employee(record):
    """Phiếu đã lưu dùng bản chụp thiết lập của chính nó để đối soát thuế/OT."""
    from copy import copy
    employee=copy(record.employee)
    employee.payroll_settings=record.breakdown.get('source_data',{}).get('employee_settings')
    return employee


@transaction.atomic
def save_employee_settings(actor, employee, settings):
    require_role(actor,HR,DIRECTOR)
    from employees.models import Employee
    from django.utils import timezone
    employee=Employee.objects.select_for_update().get(pk=employee.pk)
    from employees.forms import SalarySettingsForm
    payload={f'salary-{key}':value for key,value in settings.items()}
    for key in ['bhxh','bhyt','bhtn']:
        payload[f'salary-{key}']=Decimal(str(settings.get('insurance_rates',{}).get(key.upper(),0)))*100
    form=SalarySettingsForm(employee,data=payload)
    if not form.is_valid():
        raise ValidationError(form.errors.as_text())
    settings=form.settings_data()
    before=employee.payroll_settings
    employee.payroll_errors=[]
    comparable={key:value for key,value in (before or {}).items() if not key.startswith('_')}
    if comparable==settings:
        return employee
    employee.payroll_settings={**settings,'_updated_by':actor.pk,'_updated_at':timezone.now().isoformat()}
    employee.save(update_fields=['payroll_settings'])
    period=PayrollPeriod.objects.filter(records__employee=employee).order_by('-attendance_period__year','-attendance_period__month').first()
    if period:
        PayrollAuditLog.objects.create(period=period,actor=actor,action='employee_settings',
            reason=f'Cập nhật thiết lập tính lương dùng chung của {employee.code}',
            snapshot=[{'employee_id':employee.pk,'before':before,'after':employee.payroll_settings}])
    from .calculations import refresh_employee_payroll
    for period in PayrollPeriod.objects.filter(status='pending').select_related('attendance_period').order_by('attendance_period_id'):
        attendance=period.attendance_period
        error=refresh_employee_payroll(actor,employee.pk,attendance.year,attendance.month)
        if error: employee.payroll_errors.append(error)
    return employee


def input_snapshot(value):
    data = model_to_dict(value)
    if 'insurance_rates' in data:
        data['insurance_rates'] = {key: Decimal(str(rate)) for key, rate in data['insurance_rates'].items()}
    return canonical(data)


@transaction.atomic
def save_input(actor, value):
    require_role(actor, HR, DIRECTOR)
    link = PayrollPeriod.objects.get(pk=value.period_id)
    AttendancePeriod.objects.select_for_update().get(pk=link.attendance_period_id)
    period = PayrollPeriod.objects.select_for_update().get(pk=value.period_id)
    value.period = period
    if value.is_locked:
        raise ValidationError('Phiếu lương đã duyệt hoặc đã chi trả. Cần mở lại theo quy trình trước khi chỉnh dữ liệu.')
    before = {}
    if value.pk:
        old = type(value).objects.select_for_update().get(pk=value.pk)
        if old.period_id != value.period_id or old.employee_id != value.employee_id:
            raise ValidationError('Không được đổi kỳ hoặc nhân viên của dữ liệu đã tạo.')
        before = input_snapshot(old)
    value.full_clean()
    if before and before == input_snapshot(value):
        return value, False
    value.save()
    PayrollAuditLog.objects.create(period=period, actor=actor, action='input_' + ('tax' if hasattr(value, 'tax_amount') else 'adjustment'),
        reason='Nhân sự cập nhật dữ liệu đầu vào theo kỳ lương', snapshot=[{'before': before, 'after': input_snapshot(value)}])
    from .calculations import refresh_employee_payroll
    attendance = period.attendance_period
    value.payroll_error = refresh_employee_payroll(actor, value.employee_id, attendance.year, attendance.month)
    return value, True
