"""Tính và đối chiếu thuế TNCN theo chính sách hiện có của dự án."""
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from django.core.exceptions import ValidationError


POLICY = 'vn-resident-salary-2026-v1'


PERSONAL = Decimal(15500000)


DEPENDENT = Decimal(6200000)


MEAL_CASH_LIMIT = Decimal(1200000)


BRACKETS = [(Decimal(10000000), Decimal('.05')), (Decimal(30000000), Decimal('.10')),
            (Decimal(60000000), Decimal('.20')), (Decimal(100000000), Decimal('.30')), (None, Decimal('.35'))]


ZERO = Decimal(0)


def tinh_thue_luy_tien(income):
    income = max(ZERO, Decimal(income))
    previous, so_tien, lines = ZERO, ZERO, []
    for ceiling, ty_le in BRACKETS:
        portion = max(ZERO, (min(income, ceiling) if ceiling is not None else income) - previous)
        if portion:
            gia_tri = portion * ty_le
            lines.append({'income': str(portion), 'rate': str(ty_le), 'tax': str(gia_tri)})
            so_tien += gia_tri
        if ceiling is None or income <= ceiling:
            break
        previous = ceiling
    return so_tien.quantize(Decimal(1), rounding=ROUND_HALF_UP), lines


def tinh_thue_tncn(inputs, attendance, wage, overtime_pay, bonus, insurance, adjustments, overtime):
    if inputs.tax_method == 'legacy':
        return {'policy': 'legacy', 'tax': inputs.tax_amount}
    if inputs.tax_method != 'resident_2026':
        raise ValidationError('Chưa hỗ trợ tự tính cho chế độ thuế này. Cần đối soát riêng, không mặc định thuế bằng 0.')
    if not inputs.verified or not inputs.tax_basis.strip():
        raise ValidationError('HR cần xác nhận đủ hồ sơ và căn cứ tính thuế trước khi tính lương.')
    if attendance.nam != 2026 or attendance.thang < 7:
        raise ValidationError('Chế độ tự tính hiện hỗ trợ 07–12/2026. Kỳ khác cần cấu hình chính sách phù hợp.')
    allowances = [dong for dong in adjustments if dong.kind=='allowance']
    allowance = sum((dong.amount for dong in allowances), ZERO)
    meals = sum((dong.amount for dong in allowances if dong.tax_category == 'meal_cash'), ZERO)
    other_exempt = sum((dong.amount for dong in allowances if dong.tax_category == 'exempt'), ZERO)
    meal_exempt = min(meals, MEAL_CASH_LIMIT)
    for dong in allowances:
        if dong.tax_category != 'taxable' and not dong.basis.strip():
            raise ValidationError('Khoản không chịu thuế cần căn cứ hợp lệ: ' + dong.name)
    if inputs.tax_exempt_overtime is None:
        if any(phan_tu.get('warnings') for phan_tu in overtime):
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
    tax, brackets = tinh_thue_luy_tien(taxable)
    return {'policy': POLICY, 'tax': tax, 'taxable_income': taxable, 'taxable_gross': taxable_gross,
            'gross': wage + bonus + allowance + overtime_pay, 'insurance_deduction': insurance,
            'personal_deduction': personal, 'dependent_count': inputs.tax_dependents,
            'dependent_deduction': dependent, 'meal_cash': meals, 'meal_exempt': meal_exempt,
            'other_exempt_allowances': other_exempt, 'overtime_exempt': exempt_ot, 'brackets': brackets}


def loi_nguon_thue(record):
    """Verify new automatic tax snapshots before paying/exporting, without rewriting them."""
    da_luu = record.chi_tiet.get('tax_calculation', {})
    if da_luu.get('policy') != POLICY:
        return ''  # Historical/paid amounts remain historical; never infer a new policy for them.
    from thuong.models import Bonus, payroll_bonus_records
    from bang_cong.services.tinh_toan import tong_hop_tang_ca_tinh_luong
    from .tinh_toan import chuan_hoa_du_lieu
    attendance = record.ky_luong.attendance_period
    try:
        from .quy_trinh import can_cu_luong_nhan_vien,cac_khoan_phu_cap_khau_tru,nhan_vien_theo_phieu_luong
        nhan_vien=nhan_vien_theo_phieu_luong(record)
        inputs=can_cu_luong_nhan_vien(nhan_vien,record.ky_luong)
        adjustments=cac_khoan_phu_cap_khau_tru(nhan_vien,record.ky_luong)
        bonuses = payroll_bonus_records(Bonus.objects.filter(employee=record.nhan_vien, year=attendance.nam, month=attendance.thang))
        overtime = tong_hop_tang_ca_tinh_luong(record.nhan_vien, attendance.nam, attendance.thang)
        insurance = sum((inputs.insurance_base * Decimal(str(ty_le)) for ty_le in inputs.insurance_rates.values()), ZERO)
        exact_wage = Decimal(record.chi_tiet['attendance_pay_exact'])
        exact_ot = sum((Decimal(phan_tu['amount']) for phan_tu in record.chi_tiet.get('ot', [])), ZERO)
        chi_tiet = tinh_thue_tncn(inputs, attendance, exact_wage, exact_ot,
            sum((dong.amount for dong in bonuses), ZERO), insurance, adjustments, overtime)
        if chuan_hoa_du_lieu(chi_tiet) != da_luu or chi_tiet['tax'] != record.thue_tncn:
            return 'Dữ liệu thuế TNCN đã thay đổi. Cần mở lại và tính lại lương trước khi duyệt, xuất hoặc chi trả.'
    except (ValidationError, KeyError, ValueError, TypeError, InvalidOperation):
        return 'Thiếu hoặc sai căn cứ tính thuế TNCN. Cần kiểm tra và tính lại lương.'
    return ''
