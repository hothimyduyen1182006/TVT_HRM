from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from bang_cong.models import ChotBangCong, TongHopCong
from bang_luong.models import Luong
from nhan_vien.access import GIAM_DOC, NHAN_SU, co_vai_tro
from thuong.models import Thuong


def _so_tien(value):
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError('Thiết lập lương có giá trị tiền không hợp lệ.')


def _lam_tron(value):
    return value.quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def tinh_khau_tru_bao_hiem(nhan_vien):
    """Tính BHXH, BHYT, BHTN từ thiết lập lương trên hồ sơ nhân viên."""
    cai_dat = nhan_vien.thiet_lap_luong or {}
    luong_dong_bh = cai_dat.get('luong_dong_bao_hiem', cai_dat.get('insurance_base'))
    if luong_dong_bh is None:
        raise ValidationError(f'{nhan_vien}: chưa có mức lương đóng bảo hiểm.')

    luong_dong = _so_tien(luong_dong_bh)
    ty_le = cai_dat.get('ty_le_bao_hiem') or cai_dat.get('insurance_rates') or {}
    if luong_dong < 0:
        raise ValidationError(f'{nhan_vien}: mức lương đóng bảo hiểm không được âm.')
    for ten in ('BHXH', 'BHYT', 'BHTN'):
        if ten not in ty_le:
            raise ValidationError(f'{nhan_vien}: chưa cấu hình tỷ lệ {ten}.')
        muc = _so_tien(ty_le[ten])
        if muc < 0 or muc > 1:
            raise ValidationError(f'{nhan_vien}: tỷ lệ {ten} phải trong khoảng 0 đến 1.')

    bhxh = luong_dong * _so_tien(ty_le['BHXH'])
    bhyt = luong_dong * _so_tien(ty_le['BHYT'])
    bhtn = luong_dong * _so_tien(ty_le['BHTN'])

    return {
        'bhxh': _lam_tron(bhxh),
        'bhyt': _lam_tron(bhyt),
        'bhtn': _lam_tron(bhtn),
        'tong_bao_hiem': _lam_tron(bhxh) + _lam_tron(bhyt) + _lam_tron(bhtn),
    }


def tinh_thue_tncn(thu_nhap_chiu_thue, tong_bao_hiem, so_nguoi_phu_thuoc,
                  giam_tru_hop_le_khac=0):
    """Tính thu nhập tính thuế và thuế lũy tiến theo tháng cho cá nhân cư trú."""
    thu_nhap_tinh_thue = max(
        Decimal('0'),
        _so_tien(thu_nhap_chiu_thue)
        - _so_tien(tong_bao_hiem)
        - Decimal('15500000')
        - _so_tien(so_nguoi_phu_thuoc) * Decimal('6200000')
        - _so_tien(giam_tru_hop_le_khac),
    )

    moc_10 = Decimal('10000000')
    moc_30 = Decimal('30000000')
    moc_60 = Decimal('60000000')
    moc_100 = Decimal('100000000')

    thue = (
        min(thu_nhap_tinh_thue, moc_10) * Decimal('0.05')
        + max(min(thu_nhap_tinh_thue, moc_30) - moc_10, 0) * Decimal('0.10')
        + max(min(thu_nhap_tinh_thue, moc_60) - moc_30, 0) * Decimal('0.20')
        + max(min(thu_nhap_tinh_thue, moc_100) - moc_60, 0) * Decimal('0.30')
        + max(thu_nhap_tinh_thue - moc_100, 0) * Decimal('0.35')
    )

    return {
        'thu_nhap_tinh_thue': _lam_tron(thu_nhap_tinh_thue),
        'thue_tncn': _lam_tron(thue),
    }


def tinh_bang_luong(actor, nam, thang, reason=''):
    if not co_vai_tro(actor, NHAN_SU):
        raise PermissionDenied('Chỉ Quản lý nhân sự được tính lương.')
    if Luong.objects.filter(
        tong_hop__nam=nam, tong_hop__thang=thang,
        trang_thai=Luong.CHO_GIAM_DOC_DUYET,
    ).exists():
        raise ValidationError('Kỳ lương đã gửi Giám đốc; không thể tính lại khi đang chờ ký.')

    bang_cong = TongHopCong.objects.filter(
        nam=nam, thang=thang, approval__isnull=False,
    ).select_related('nhan_vien__nguoi_dung')
    if not bang_cong.exists():
        raise ValidationError('Kỳ này chưa có bảng công nào được chốt.')

    with transaction.atomic():
        so_phieu_da_tinh = 0
        da_khoa = set(Luong.objects.filter(
            tong_hop__in=bang_cong,
            trang_thai__in=[
                Luong.CHO_GIAM_DOC_DUYET, Luong.DA_DUYET,
            ],
        ).values_list('tong_hop_id', flat=True))

        for cong in bang_cong:
            if cong.pk in da_khoa:
                continue
            if cong.cong_chuan <= 0:
                raise ValidationError(f'{cong.nhan_vien}: công chuẩn phải lớn hơn 0.')

            nhan_vien = cong.nhan_vien
            cai_dat = nhan_vien.thiet_lap_luong or {}
            if cai_dat.get('doi_tuong_tinh_thue', cai_dat.get('tax_method')) != 'resident_2026':
                raise ValidationError(f'{nhan_vien}: chỉ tự tính thuế cho cấu hình cá nhân cư trú 2026.')
            if _so_tien(nhan_vien.luong_co_ban) <= 0:
                raise ValidationError(f'{nhan_vien}: lương cơ bản phải lớn hơn 0.')
            if not str(cai_dat.get('can_cu_bao_hiem', cai_dat.get('insurance_basis', ''))).strip():
                raise ValidationError(f'{nhan_vien}: chưa ghi căn cứ lương đóng bảo hiểm.')
            if not str(cai_dat.get('can_cu_thue', cai_dat.get('tax_basis', ''))).strip():
                raise ValidationError(f'{nhan_vien}: chưa ghi căn cứ tính thuế.')
            try:
                so_nguoi_phu_thuoc = int(cai_dat.get('so_nguoi_phu_thuoc', cai_dat.get('tax_dependents', 0)))
            except (TypeError, ValueError):
                raise ValidationError(f'{nhan_vien}: số người phụ thuộc không hợp lệ.')
            if so_nguoi_phu_thuoc < 0:
                raise ValidationError(f'{nhan_vien}: số người phụ thuộc không được âm.')

            try:
                thuong = Thuong.objects.get(
                    nguoi_dung=nhan_vien.nguoi_dung,
                    nam=nam,
                    thang=thang,
                    trang_thai='approved',
                )
            except Thuong.DoesNotExist:
                raise ValidationError(f'{nhan_vien}: chưa có bảng thưởng đã duyệt cho kỳ này.')
            if (thuong.nguoi_dung_id != nhan_vien.nguoi_dung_id
                    or thuong.nam != nam or thuong.thang != thang):
                raise ValidationError(f'{nhan_vien}: bảng thưởng không khớp nhân viên hoặc kỳ lương.')

            luong_co_ban = _so_tien(nhan_vien.luong_co_ban)
            luong_theo_cong = (
                luong_co_ban * _so_tien(cong.tong_cong) / _so_tien(cong.cong_chuan)
            )
            gio_ot = _so_tien(cong.tong_gio_tang_ca)
            don_gia_ot = _so_tien(cai_dat.get('luong_gio_tang_ca', cai_dat.get('overtime_hourly_rate')))
            if gio_ot and don_gia_ot <= 0:
                raise ValidationError(f'{nhan_vien}: thiếu đơn giá giờ tăng ca.')
            if gio_ot and not str(cai_dat.get('can_cu_luong_gio_tang_ca', cai_dat.get('overtime_basis', ''))).strip():
                raise ValidationError(f'{nhan_vien}: chưa ghi căn cứ đơn giá tăng ca.')

            luong_tang_ca = gio_ot * don_gia_ot
            phu_cap = _so_tien(cai_dat.get('phu_cap_an_trua', cai_dat.get('lunch_allowance')))
            if phu_cap < 0:
                raise ValidationError(f'{nhan_vien}: phụ cấp không được âm.')
            tong_thuong = _so_tien(thuong.tong_thuong)
            bao_hiem = tinh_khau_tru_bao_hiem(nhan_vien)
            tong_thu_nhap = luong_theo_cong + luong_tang_ca + phu_cap + tong_thuong
            thue = tinh_thue_tncn(
                tong_thu_nhap,
                bao_hiem['tong_bao_hiem'],
                so_nguoi_phu_thuoc,
            )
            thuc_linh = (
                tong_thu_nhap - bao_hiem['tong_bao_hiem'] - thue['thue_tncn']
            )

            Luong.objects.update_or_create(
                tong_hop=cong,
                defaults={
                    'tong_thuong': thuong,
                    'luong_co_ban': _lam_tron(luong_co_ban),
                    'luong_theo_cong': _lam_tron(luong_theo_cong),
                    'luong_tang_ca': _lam_tron(luong_tang_ca),
                    'phu_cap': _lam_tron(phu_cap),
                    'tong_tien_thuong': _lam_tron(tong_thuong),
                    'khau_tru_di_tre': 0,
                    'khau_tru_bhxh': bao_hiem['tong_bao_hiem'],
                    'khau_tru_khac': 0,
                    'thue_tncn': thue['thue_tncn'],
                    'luong_thuc_linh': _lam_tron(thuc_linh),
                    'trang_thai': Luong.CHO_DUYET,
                },
            )
            so_phieu_da_tinh += 1
    return so_phieu_da_tinh


@transaction.atomic
def gui_bang_luong_cho_giam_doc(actor, nam, thang):
    if not co_vai_tro(actor, NHAN_SU):
        raise PermissionDenied('Chỉ Quản lý nhân sự được gửi bảng lương.')

    phieu_luong = Luong.objects.select_for_update().filter(
        tong_hop__nam=nam, tong_hop__thang=thang,
    ).order_by('pk')
    if not phieu_luong.exists():
        raise ValidationError('Kỳ này chưa có phiếu lương để gửi duyệt.')
    so_bang_cong = TongHopCong.objects.filter(
        nam=nam, thang=thang, approval__isnull=False,
    ).count()
    if phieu_luong.count() != so_bang_cong:
        raise ValidationError('Hãy tính đủ phiếu cho tất cả bảng công đã chốt trước khi gửi.')
    if phieu_luong.exclude(trang_thai=Luong.CHO_DUYET).exists():
        raise ValidationError('Tất cả phiếu trong kỳ phải ở trạng thái chờ nhân sự kiểm tra.')

    so_phieu = phieu_luong.update(trang_thai=Luong.CHO_GIAM_DOC_DUYET)
    return so_phieu


@transaction.atomic
def duyet_toan_bo_bang_luong(actor, nam, thang):
    if not co_vai_tro(actor, GIAM_DOC):
        raise PermissionDenied('Chỉ Giám đốc được ký duyệt bảng lương.')

    phieu_luong = Luong.objects.select_for_update().filter(
        tong_hop__nam=nam, tong_hop__thang=thang,
    ).order_by('pk')
    if not phieu_luong.exists():
        raise ValidationError('Kỳ này chưa có phiếu lương để duyệt.')
    so_bang_cong = TongHopCong.objects.filter(
        nam=nam, thang=thang, approval__isnull=False,
    ).count()
    if phieu_luong.count() != so_bang_cong:
        raise ValidationError('Số phiếu lương không khớp với các bảng công đã chốt.')
    if phieu_luong.exclude(trang_thai=Luong.CHO_GIAM_DOC_DUYET).exists():
        raise ValidationError('Tất cả phiếu trong kỳ phải được nhân sự gửi chờ Giám đốc ký.')

    so_phieu = phieu_luong.update(trang_thai=Luong.DA_DUYET)
    return so_phieu


def cap_nhat_luong_nhan_vien(actor, employee_id, year, month):
    """Bảo vệ phiếu đã duyệt khi app nguồn thay đổi dữ liệu."""
    if not co_vai_tro(actor, NHAN_SU, GIAM_DOC):
        raise PermissionDenied('Chỉ Quản lý nhân sự hoặc Giám đốc được cập nhật bảng lương.')
    phieu = Luong.objects.filter(
        tong_hop__nhan_vien_id=employee_id,
        tong_hop__nam=year,
        tong_hop__thang=month,
        trang_thai=Luong.CHO_DUYET,
    ).first()
    if phieu:
        return 'Phiếu lương đang chờ duyệt cần được kiểm tra và tính lại theo quy tắc lương đã được xác nhận.'
    return ''
