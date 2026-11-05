"""Chuẩn bị dữ liệu phiếu lương từ kết quả đã lưu; không tính hoặc cập nhật lương."""
from decimal import Decimal
from django.db.models import Sum, Count, Q
from attendance.models import AttendanceRecord


def payslip_context(record):
    breakdown = record.breakdown
    insurance = []
    rates = breakdown.get('insurance_rates', {})
    for name, amount in breakdown.get('insurance', {}).items():
        rate = rates.get(name)
        insurance.append({'name': name, 'amount': Decimal(str(amount)),
                          'percent': Decimal(str(rate)) * 100 if rate is not None else None})
    # Model hiện không phân loại riêng phạt đi trễ. Không lấy tổng deductions giả làm phạt.
    # Giữ tổng khấu trừ đã lưu; chi tiết khoản được duyệt nằm trong breakdown.adjustments.
    total_income = record.attendance_pay + record.ot_pay + record.bonus_pay + record.allowance
    total_deductions = record.insurance + record.tax + record.deductions
    metrics = {'actual': None, 'absent': None, 'late_count': None}
    period = record.period
    attendance = period.attendance_period
    employee_approved = attendance.employee_approvals.filter(employee_id=record.employee_id).exists()
    if attendance.status == 'approved' or employee_approved:
        data = AttendanceRecord.objects.filter(employee_id=record.employee_id,
            date__year=attendance.year, date__month=attendance.month).aggregate(
                actual=Sum('actual_units'), absent=Count('pk', filter=Q(status='absent')),
                late_count=Count('pk', filter=Q(late_minutes__gt=0)))
        metrics = data
    return {'row': record, 'income_total': total_income, 'deductions_total': total_deductions,
            'insurance_lines': insurance, 'metrics': metrics,
            'adjustments': breakdown.get('adjustments', []),
            'payment_label': {'pending': 'Chờ duyệt · Chưa chi trả',
                              'approved': 'Đã duyệt · Chưa chi trả', 'paid': 'Đã chi trả'}[record.status]}
