"""Monthly resident salary withholding: Law 109/2025 and Decree 253/2026.

Scope: July–December 2026, resident employees with contracts >= 3 months.
Other regimes require separate assessment; this is not an annual tax settlement.
"""
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from django.core.exceptions import ValidationError

POLICY = 'vn-resident-salary-2026-v1'
PERSONAL = Decimal(15500000)
DEPENDENT = Decimal(6200000)
MEAL_CASH_LIMIT = Decimal(1200000)
BRACKETS = [(Decimal(10000000), Decimal('.05')), (Decimal(30000000), Decimal('.10')),
            (Decimal(60000000), Decimal('.20')), (Decimal(100000000), Decimal('.30')), (None, Decimal('.35'))]
ZERO = Decimal(0)


def progressive_tax(income):
    income = max(ZERO, Decimal(income))
    previous, amount, lines = ZERO, ZERO, []
    for ceiling, rate in BRACKETS:
        portion = max(ZERO, (min(income, ceiling) if ceiling is not None else income) - previous)
        if portion:
            value = portion * rate
            lines.append({'income': str(portion), 'rate': str(rate), 'tax': str(value)})
            amount += value
        if ceiling is None or income <= ceiling:
            break
        previous = ceiling
    return amount.quantize(Decimal(1), rounding=ROUND_HALF_UP), lines


def calculate_tax(inputs, attendance, wage, overtime_pay, bonus, insurance, adjustments, overtime):
    if inputs.tax_method == 'legacy':
        return {'policy': 'legacy', 'tax': inputs.tax_amount}
    if inputs.tax_method != 'resident_2026':
        raise ValidationError('Chưa hỗ trợ tự tính cho chế độ thuế này. Cần đối soát riêng, không mặc định thuế bằng 0.')
    if not inputs.verified or not inputs.tax_basis.strip():
        raise ValidationError('HR cần xác nhận đủ hồ sơ và căn cứ tính thuế trước khi tính lương.')
    if attendance.year != 2026 or attendance.month < 7:
        raise ValidationError('Chế độ tự tính hiện hỗ trợ 07–12/2026. Kỳ khác cần cấu hình chính sách phù hợp.')
    allowances = list(adjustments.filter(kind='allowance'))
    allowance = sum((row.amount for row in allowances), ZERO)
    meals = sum((row.amount for row in allowances if row.tax_category == 'meal_cash'), ZERO)
    other_exempt = sum((row.amount for row in allowances if row.tax_category == 'exempt'), ZERO)
    meal_exempt = min(meals, MEAL_CASH_LIMIT)
    for row in allowances:
        if row.tax_category != 'taxable' and not row.basis.strip():
            raise ValidationError('Khoản không chịu thuế cần căn cứ hợp lệ: ' + row.name)
    if inputs.tax_exempt_overtime is None:
        if any(item.get('warnings') for item in overtime):
            raise ValidationError('OT có cảnh báo hạn mức; HR cần đối soát và nhập số tiền OT đủ điều kiện miễn thuế.')
        exempt_ot = overtime_pay
    else:
        exempt_ot = inputs.tax_exempt_overtime
        if exempt_ot > overtime_pay:
            raise ValidationError('Tiền OT miễn thuế không được vượt tiền OT thực tế.')
    taxable_gross = max(ZERO, wage + bonus + allowance + overtime_pay - exempt_ot - meal_exempt - other_exempt)
    personal = PERSONAL if inputs.claim_personal_deduction else ZERO
    dependent = DEPENDENT * inputs.tax_dependents
    taxable = max(ZERO, taxable_gross - insurance - personal - dependent)
    tax, brackets = progressive_tax(taxable)
    return {'policy': POLICY, 'tax': tax, 'taxable_income': taxable, 'taxable_gross': taxable_gross,
            'gross': wage + bonus + allowance + overtime_pay, 'insurance_deduction': insurance,
            'personal_deduction': personal, 'dependent_count': inputs.tax_dependents,
            'dependent_deduction': dependent, 'meal_cash': meals, 'meal_exempt': meal_exempt,
            'other_exempt_allowances': other_exempt, 'overtime_exempt': exempt_ot, 'brackets': brackets}


def tax_source_error(record):
    """Verify new automatic tax snapshots before paying/exporting, without rewriting them."""
    saved = record.breakdown.get('tax_calculation', {})
    if saved.get('policy') != POLICY:
        return ''  # Historical/paid amounts remain historical; never infer a new policy for them.
    from payroll.models import PayrollInput, PayrollAdjustment
    from bonuses.models import Bonus, payroll_bonus_records
    from attendance.services.calculations import payroll_overtime
    from .source_data import canonical
    attendance = record.period.attendance_period
    try:
        inputs = PayrollInput.objects.get(period=record.period, employee=record.employee, verified=True)
        adjustments = PayrollAdjustment.objects.filter(period=record.period, employee=record.employee, approved=True)
        bonuses = payroll_bonus_records(Bonus.objects.filter(employee=record.employee, year=attendance.year, month=attendance.month))
        overtime = payroll_overtime(record.employee, attendance.year, attendance.month)
        insurance = sum((inputs.insurance_base * Decimal(str(rate)) for rate in inputs.insurance_rates.values()), ZERO)
        exact_wage = Decimal(record.breakdown['attendance_pay_exact'])
        exact_ot = sum((Decimal(item['amount']) for item in record.breakdown.get('ot', [])), ZERO)
        details = calculate_tax(inputs, attendance, exact_wage, exact_ot,
            sum((row.amount for row in bonuses), ZERO), insurance, adjustments, overtime)
        if canonical(details) != saved or details['tax'] != record.tax:
            return 'Dữ liệu thuế TNCN đã thay đổi. Cần mở lại và tính lại lương trước khi duyệt, xuất hoặc chi trả.'
    except (ValidationError, PayrollInput.DoesNotExist, KeyError, ValueError, TypeError, InvalidOperation):
        return 'Thiếu hoặc sai căn cứ tính thuế TNCN. Cần kiểm tra và tính lại lương.'
    return ''
