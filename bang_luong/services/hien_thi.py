"""Lọc phiếu lương, chuẩn bị nội dung hiển thị và xuất dữ liệu."""
import csv
import io
import json
from decimal import Decimal
from django.db.models import Sum, Count, Q, Exists, OuterRef
from bang_cong.models import ChamCong, ChotBangCong
from bang_luong.models import Luong
from bang_cong.thang_lich import thang_lich
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from nhan_vien.access import yeu_cau_vai_tro, NHAN_SU, GIAM_DOC


def phieu_luong_du_cong_duyet(queryset):
    """Giữ phiếu cũ trong database, chỉ công bố khi công đã duyệt."""
    ban_chot = ChotBangCong.objects.filter(
        tong_hop__nam=OuterRef('tong_hop__nam'),
        tong_hop__thang=OuterRef('tong_hop__thang'),
        tong_hop__nhan_vien_id=OuterRef('tong_hop__nhan_vien_id'),
    )
    return queryset.annotate(cong_da_duyet=Exists(ban_chot)).filter(cong_da_duyet=True)


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
    ky_cong = thang_lich(record.tong_hop.nam, record.tong_hop.thang)
    employee_approved = ky_cong.employee_approvals.filter(tong_hop__nhan_vien_id=record.nhan_vien_id).exists()
    if ky_cong.trang_thai == 'approved' or employee_approved:
        from bang_cong.services.tinh_toan import nap_cong_ngay

        ds_cong = list(ChamCong.objects.filter(nhan_vien_id=record.nhan_vien_id,
            ngay__year=ky_cong.nam, ngay__month=ky_cong.thang))
        nap_cong_ngay(ds_cong, ky_cong)
        metrics = {'actual': sum((r.cong_thuc_te for r in ds_cong), Decimal(0)),
                   'absent': sum(r.trang_thai == 'absent' for r in ds_cong),
                   'late_count': sum(r.so_phut_tre > 0 for r in ds_cong)}
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
    ds_dong = Luong.objects.select_related('tong_hop', 'tong_hop__nhan_vien').filter(
        tong_hop__nhan_vien__in=form.nhan_vien_trong_pham_vi(user),
        tong_hop__thang=du_lieu['month'], tong_hop__nam=du_lieu['year'])
    if du_lieu.get('q'):
        ds_dong = ds_dong.filter(
            Q(tong_hop__nhan_vien__ho_va_ten__icontains=du_lieu['q']) |
            Q(tong_hop__nhan_vien__ma_ho_so__icontains=du_lieu['q']))
    if du_lieu.get('status'):
        ds_dong = ds_dong.filter(trang_thai=du_lieu['status'])
    return phieu_luong_du_cong_duyet(ds_dong)


def phieu_luong_ca_nhan(user):
    """Phiếu lương của tài khoản hiện tại, không mở rộng theo vai trò quản lý."""
    return phieu_luong_du_cong_duyet(
        Luong.objects.select_related('tong_hop', 'tong_hop__nhan_vien').filter(
            tong_hop__nhan_vien__nguoi_dung=user),
    )


FIELDS = ['ma_nhan_vien', 'ten_nhan_vien', 'ten_phong_ban', 'luong_co_ban', 'cong_chuan',
          'cong_nghi_phep', 'cong_huong_luong', 'luong_theo_cong', 'tong_tien_thuong', 'so_phut_tre', 'khau_tru_di_tre',
          'phu_cap', 'tong_bao_hiem', 'thue_tncn', 'tong_khau_tru', 'luong_thuc_linh']


def o_du_lieu_an_toan(value):
    # Không để tên/ghi chú do người dùng nhập trở thành công thức khi mở CSV.
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value


@transaction.atomic
def xuat_du_lieu_luong(actor, queryset, fmt, month, year, scope):
    yeu_cau_vai_tro(actor, NHAN_SU, GIAM_DOC)
    if queryset.exclude(pk__in=phieu_luong_du_cong_duyet(queryset).values('pk')).exists():
        raise ValidationError('Bảng công chưa duyệt, không được xuất phiếu lương.')
    if fmt not in ['csv', 'json', 'txt']:
        raise ValidationError('Định dạng không hợp lệ.')
    ds_dong = list(queryset.select_for_update().select_related('tong_hop', 'tong_hop__nhan_vien')
                    .order_by('tong_hop__nhan_vien__ma_ho_so'))
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
    response = HttpResponse(content, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="payroll-{year}-{month:02}.{fmt}"'
    return response
