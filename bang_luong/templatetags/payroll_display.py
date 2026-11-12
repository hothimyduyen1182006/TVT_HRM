from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django import template

register = template.Library()


@register.filter
def money(value):
    """Chỉ định dạng hiển thị; không ghi đè số tiền đã lưu."""
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            return '—'
        return format(amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP), ',.0f')
    except (InvalidOperation, TypeError, ValueError):
        return '—'


@register.filter
def units(value):
    if value is None:
        return '—'
    try:
        return format(Decimal(str(value)), 'f').rstrip('0').rstrip('.') if '.' in str(value) else str(value)
    except (InvalidOperation, TypeError, ValueError):
        return '—'


@register.filter
def department_tone(value):
    """Màu ổn định theo phòng, không hardcode tên phòng của dữ liệu mẫu."""
    return sum(ord(char) for char in str(value)) % 6


@register.filter
def bhxh(record):
    # Chỉ đọc khoản có mã BHXH rõ ràng; không suy diễn từ tổng bảo hiểm.
    return record.breakdown.get('insurance', {}).get('BHXH')
