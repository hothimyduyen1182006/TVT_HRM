"""Lọc dữ liệu và chuẩn bị nội dung hiển thị; không ghi hoặc tính lại lương."""
from decimal import Decimal

from django.db.models import Sum, Count, Q

from bang_cong.models import ChamCong
from bang_luong.models import PayrollRecord


def payslip_context(record):
    breakdown = record.breakdown
    insurance = []
    rates = breakdown.get('insurance_rates', {})
    for name, amount in breakdown.get('insurance', {}).items():
        rate = rates.get(name)
        insurance.append({'name': name, 'amount': Decimal(str(amount)),
                          'percent': Decimal(str(rate)) * 100 if rate is not None else None})
    # Hiển thị khoản phạt từ snapshot; không tính lại phiếu lịch sử khi xem.
    total_income = record.attendance_pay + record.bonus_pay + record.allowance
    historical_overtime = bool((record.ot_hours or record.ot_pay) and
        record.breakdown.get('source_data',{}).get('overtime_policy')!='automatic-checkout-1700-v1')
    if record.ot_pay:
        total_income += record.ot_pay  # Đối chiếu phiếu cũ; tuyệt đối không tính lại số tiền đã lưu.
    total_deductions = record.insurance + record.tax + record.deductions
    metrics = {'actual': None, 'absent': None, 'late_count': None}
    period = record.period
    attendance = period.attendance_period
    employee_approved = attendance.employee_approvals.filter(nhan_vien_id=record.employee_id).exists()
    if attendance.trang_thai == 'approved' or employee_approved:
        data = ChamCong.objects.filter(nhan_vien_id=record.employee_id,
            ngay__year=attendance.nam, ngay__month=attendance.thang).aggregate(
                actual=Sum('cong_thuc_te'), absent=Count('pk', filter=Q(trang_thai='absent')),
                late_count=Count('pk', filter=Q(so_phut_tre__gt=0)))
        metrics = data
    return {'row': record, 'income_total': total_income, 'historical_overtime': historical_overtime,
            'deductions_total': total_deductions,
            'insurance_lines': insurance, 'metrics': metrics,
            'adjustments': breakdown.get('adjustments', []),
            'payment_label': {'pending': 'Chờ duyệt · Chưa chi trả',
                              'approved': 'Đã duyệt · Chưa chi trả', 'paid': 'Đã chi trả'}[record.status]}


def scoped_records(user, form):
    """Giữ phạm vi nhân viên được phép xem trước khi áp dụng bộ lọc lương."""
    if not form.is_valid():
        return PayrollRecord.objects.none()
    data = form.cleaned_data
    rows = PayrollRecord.objects.select_related('period__attendance_period').filter(
        employee__in=form.employee_scope(user), period__attendance_period__thang=data['month'],
        period__attendance_period__nam=data['year'])
    if data.get('q'):
        rows = rows.filter(Q(employee_name__icontains=data['q']) | Q(employee_code__icontains=data['q']))
    if data.get('status'):
        rows = rows.filter(status=data['status'])
    return rows


def employee_records(user):
    """Phiếu lương của tài khoản hiện tại, không mở rộng theo vai trò quản lý."""
    return PayrollRecord.objects.select_related('period__attendance_period').filter(employee__user=user)
