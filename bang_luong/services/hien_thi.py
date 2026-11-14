"""Lọc phiếu lương, chuẩn bị nội dung hiển thị và xuất dữ liệu."""
import csv
import io
import json
from decimal import Decimal
from django.db.models import Sum, Count, Q, Exists, OuterRef
from bang_cong.models import ChamCong, ChotBangCong
from bang_luong.models import Luong, PayrollAuditLog, PayrollPeriod
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from nhan_vien.access import require_role, HR, DIRECTOR


def phieu_luong_du_cong_duyet(queryset):
    """Giữ phiếu cũ trong database, chỉ công bố khi công đã duyệt."""
    ban_chot = ChotBangCong.objects.filter(
        ky_cong_id=OuterRef('ky_luong__attendance_period_id'),
        nhan_vien_id=OuterRef('nhan_vien_id'),
    )
    return queryset.annotate(cong_da_duyet=Exists(ban_chot)).filter(
        Q(ky_luong__attendance_period__trang_thai='approved') | Q(cong_da_duyet=True),
    )


def du_lieu_hien_thi_luong(record):
    chi_tiet = record.chi_tiet
    bao_hiem = []
    cac_ty_le = chi_tiet.get('insurance_rates', {})
    for ten, so_tien in chi_tiet.get('insurance', {}).items():
        ty_le = cac_ty_le.get(ten)
        bao_hiem.append({'name': ten, 'amount': Decimal(str(so_tien)),
                          'percent': Decimal(str(ty_le)) * 100 if ty_le is not None else None})
    # Hiển thị khoản phạt từ snapshot; không tính lại phiếu lịch sử khi xem.
    tong_thu_nhap = record.luong_theo_cong + record.tong_tien_thuong + record.phu_cap
    tang_ca_lich_su = bool((record.so_gio_tang_ca or record.luong_tang_ca) and
        record.chi_tiet.get('source_data',{}).get('overtime_policy')!='automatic-checkout-1700-v1')
    if record.luong_tang_ca:
        tong_thu_nhap += record.luong_tang_ca  # Đối chiếu phiếu cũ; tuyệt đối không tính lại số tiền đã lưu.
    total_deductions = record.tong_bao_hiem + record.thue_tncn + record.tong_khau_tru
    metrics = {'actual': None, 'absent': None, 'late_count': None}
    ky_luong = record.ky_luong
    ky_cong = ky_luong.attendance_period
    employee_approved = ky_cong.employee_approvals.filter(nhan_vien_id=record.nhan_vien_id).exists()
    if ky_cong.trang_thai == 'approved' or employee_approved:
        du_lieu = ChamCong.objects.filter(nhan_vien_id=record.nhan_vien_id,
            ngay__year=ky_cong.nam, ngay__month=ky_cong.thang).aggregate(
                actual=Sum('cong_thuc_te'), absent=Count('pk', filter=Q(trang_thai='absent')),
                late_count=Count('pk', filter=Q(so_phut_tre__gt=0)))
        metrics = du_lieu
    return {'row': record, 'income_total': tong_thu_nhap, 'historical_overtime': tang_ca_lich_su,
            'deductions_total': total_deductions,
            'insurance_lines': bao_hiem, 'metrics': metrics,
            'adjustments': chi_tiet.get('adjustments', []),
            'payment_label': {'pending': 'Chờ duyệt · Chưa chi trả',
                              'approved': 'Đã duyệt · Chưa chi trả', 'paid': 'Đã chi trả'}[record.trang_thai]}


def phieu_luong_trong_pham_vi(user, form):
    """Giữ phạm vi nhân viên được phép xem trước khi áp dụng bộ lọc lương."""
    if not form.is_valid():
        return Luong.objects.none()
    du_lieu = form.cleaned_data
    ds_dong = Luong.objects.select_related('ky_luong__attendance_period').filter(
        nhan_vien__in=form.employee_scope(user), ky_luong__attendance_period__thang=du_lieu['month'],
        ky_luong__attendance_period__nam=du_lieu['year'])
    if du_lieu.get('q'):
        ds_dong = ds_dong.filter(Q(ten_nhan_vien__icontains=du_lieu['q']) | Q(ma_nhan_vien__icontains=du_lieu['q']))
    if du_lieu.get('status'):
        ds_dong = ds_dong.filter(trang_thai=du_lieu['status'])
    return phieu_luong_du_cong_duyet(ds_dong)


def phieu_luong_ca_nhan(user):
    """Phiếu lương của tài khoản hiện tại, không mở rộng theo vai trò quản lý."""
    return phieu_luong_du_cong_duyet(
        Luong.objects.select_related('ky_luong__attendance_period').filter(nhan_vien__user=user),
    )


FIELDS = ['ma_nhan_vien', 'ten_nhan_vien', 'ten_phong_ban', 'luong_co_ban', 'cong_chuan',
          'cong_nghi_phep', 'cong_huong_luong', 'luong_theo_cong', 'tong_tien_thuong', 'so_phut_tre', 'khau_tru_di_tre',
          'phu_cap', 'tong_bao_hiem', 'thue_tncn', 'tong_khau_tru', 'luong_thuc_linh']


def o_du_lieu_an_toan(value):
    # Không để tên/ghi chú do người dùng nhập trở thành công thức khi mở CSV.
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value


@transaction.atomic
def xuat_du_lieu_luong(actor, queryset, fmt, month, year, scope):
    require_role(actor, HR, DIRECTOR)
    if queryset.exclude(pk__in=phieu_luong_du_cong_duyet(queryset).values('pk')).exists():
        raise ValidationError('Bảng công chưa duyệt, không được xuất phiếu lương.')
    if fmt not in ['csv', 'json', 'txt']:
        raise ValidationError('Định dạng không hợp lệ.')
    period_ids = list(queryset.values_list('ky_luong_id', flat=True).distinct())
    # Giữ khóa trạng thái đến khi tạo nội dung và log, tránh xuất cùng lúc mở lại kỳ.
    list(PayrollPeriod.objects.select_for_update().filter(pk__in=period_ids).order_by('pk'))
    ds_dong = list(queryset.select_related('ky_luong').order_by('ma_nhan_vien'))
    if not ds_dong:
        raise ValidationError('Không có dữ liệu để xuất.')
    if any(row.trang_thai not in ['approved', 'paid'] for row in ds_dong):
        raise ValidationError('Không xuất bảng lương chưa duyệt.')
    from .quy_trinh import loi_nguon_tang_ca
    from .thue import loi_nguon_thue
    for row in ds_dong:
        if row.trang_thai!='paid':
            loi=loi_nguon_tang_ca(row) or loi_nguon_thue(row)
            if loi:
                raise ValidationError(loi)
    from bang_cong.services.tinh_toan import CHINH_SACH_OT
    def is_historical(row):
        return row.chi_tiet.get('source_data', {}).get('overtime_policy') != CHINH_SACH_OT
    historical = any((row.so_gio_tang_ca or row.luong_tang_ca) and is_historical(row) for row in ds_dong)
    current_ot = any((row.so_gio_tang_ca or row.luong_tang_ca) and not is_historical(row) for row in ds_dong)
    cac_truong = FIELDS + (['ot_hours', 'ot_pay'] if current_ot else []) + (
        ['historical_ot_hours', 'historical_ot_pay'] if historical else [])
    du_lieu = []
    for row in ds_dong:
        phan_tu = {ten: str(getattr(row, ten)) for ten in FIELDS}
        if current_ot:
            phan_tu.update(ot_hours=str(row.so_gio_tang_ca) if not is_historical(row) else '0',
                        ot_pay=str(row.luong_tang_ca) if not is_historical(row) else '0')
        if historical:
            phan_tu.update(historical_ot_hours=str(row.so_gio_tang_ca) if is_historical(row) else '0',
                        historical_ot_pay=str(row.luong_tang_ca) if is_historical(row) else '0')
        du_lieu.append({**phan_tu, 'status': row.get_trang_thai_display(), 'breakdown': row.chi_tiet})
    if fmt == 'json':
        content = json.dumps(du_lieu, ensure_ascii=False, indent=2)
        content_type = 'application/json; charset=utf-8'
    else:
        output = io.StringIO(newline='')
        writer = csv.writer(output, delimiter=',' if fmt == 'csv' else '\t')
        writer.writerow(cac_truong + ['status'])
        for row in du_lieu:
            writer.writerow([o_du_lieu_an_toan(row[khoa]) for khoa in cac_truong + ['status']])
        content = ('\ufeff' if fmt == 'csv' else '') + output.getvalue()
        content_type = 'text/csv; charset=utf-8' if fmt == 'csv' else 'text/plain; charset=utf-8'
    for period_id in period_ids:
        PayrollAuditLog.objects.create(
            actor=actor, period_id=period_id, action='export',
            reason=f'Export {fmt} {month:02}/{year}',
            snapshot=[{'format': fmt, 'month': month, 'year': year,
                       'scope': {**scope, 'record_ids': [row.pk for row in ds_dong if row.ky_luong_id == period_id]}}],
        )
    response = HttpResponse(content, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="payroll-{year}-{month:02}.{fmt}"'
    return response
