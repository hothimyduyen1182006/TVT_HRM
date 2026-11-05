from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms.models import model_to_dict
from employees.access import require_role, HR, DIRECTOR
from payroll.models import PayrollPeriod, PayrollAuditLog
from .source_data import canonical


def input_snapshot(value):
    data = model_to_dict(value)
    if 'insurance_rates' in data:
        data['insurance_rates'] = {key: Decimal(str(rate)) for key, rate in data['insurance_rates'].items()}
    return canonical(data)


@transaction.atomic
def save_input(actor, value):
    require_role(actor, HR, DIRECTOR)
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
    return value, True
