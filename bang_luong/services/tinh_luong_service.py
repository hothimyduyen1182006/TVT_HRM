from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from bang_cong.models import TongHopCong
from bang_luong.models import Luong
from nhan_vien.access import GIAM_DOC, NHAN_SU, co_vai_tro
from thuong.models import Thuong


def _so_tien(value):
    try:
        return Decimal(str(value or 0))
    except InvalidOperation:
        raise ValidationError('Thiết lập lương có giá trị tiền không hợp lệ.') from None


def _lam_tron(value):
    return value.quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def tinh_khau_tru_bao_hiem(nhan_vien):
    """Tính tổng bảo hiểm nhân viên phải đóng."""
    cai_dat = nhan_vien.thiet_lap_luong or {}
    luong_dong_bh = _so_tien(cai_dat.get('luong_dong_bao_hiem'))

    if luong_dong_bh <= 0:
        raise ValidationError('Lương đóng bảo hiểm phải lớn hơn 0.')

    tong_bao_hiem = luong_dong_bh * Decimal('0.105')
    return _lam_tron(tong_bao_hiem)


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



def _tinh_phieu_luong(cong):
    nhan_vien = cong.nhan_vien
    cai_dat = nhan_vien.thiet_lap_luong or {}

    # Kiểm tra công chuẩn
    if cong.cong_chuan <= 0:
        raise ValidationError('Công chuẩn phải lớn hơn 0.')

    # Lấy bảng thưởng đã duyệt
    try:
        thuong = Thuong.objects.get(
            nguoi_dung=nhan_vien.nguoi_dung,
            nam=cong.nam,
            thang=cong.thang,
            trang_thai='da_duyet'
        )
    except Thuong.DoesNotExist:
        raise ValidationError('Nhân viên chưa có bảng thưởng đã duyệt.')

    # 1. Tính lương theo công
    luong_co_ban = _so_tien(nhan_vien.luong_co_ban)
    luong_theo_cong = luong_co_ban * _so_tien(cong.tong_cong) / _so_tien(cong.cong_chuan)

    # 2. Tính lương tăng ca
    gio_ot = _so_tien(cong.tong_gio_tang_ca)
    don_gia_ot = _so_tien(cai_dat.get('luong_gio_tang_ca', 0))
    luong_tang_ca = gio_ot * don_gia_ot

    # 3. Phụ cấp và thưởng
    phu_cap = _so_tien(cai_dat.get('phu_cap_an_trua', 0))
    tong_thuong = _so_tien(thuong.tong_thuong)

    # 4. Tổng thu nhập
    tong_thu_nhap = luong_theo_cong + luong_tang_ca + phu_cap + tong_thuong

    # 5. Tính bảo hiểm
    tong_bao_hiem = tinh_khau_tru_bao_hiem(nhan_vien)

    # 6. Tính thuế TNCN
    so_nguoi_phu_thuoc = int(cai_dat.get('so_nguoi_phu_thuoc', 0))
    thue = tinh_thue_tncn(
        tong_thu_nhap,
        tong_bao_hiem,
        so_nguoi_phu_thuoc
    )

    # 7. Tính lương thực lĩnh
    thuc_linh = tong_thu_nhap - tong_bao_hiem - thue['thue_tncn']

    # 8. Lưu phiếu lương
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
            'khau_tru_bhxh': tong_bao_hiem,
            'khau_tru_khac': 0,
            'thue_tncn': thue['thue_tncn'],
            'luong_thuc_linh': _lam_tron(thuc_linh),
            'trang_thai': 'Cho_duyet'
        }
    )


def tinh_bang_luong(actor, nam, thang):

    # Kiểm tra quyền nhân sự
    if not co_vai_tro(actor, NHAN_SU):
        raise PermissionDenied('Chỉ Quản lý nhân sự được tính lương.')

    # Lấy bảng công đã chốt
    bang_cong = TongHopCong.objects.filter(
        nam=nam,
        thang=thang,
        chotbangcong__isnull=False
    )

    if not bang_cong.exists():
        raise ValidationError('Chưa có bảng công được chốt.')

    so_phieu_da_tinh = 0

    with transaction.atomic():
        for cong in bang_cong:

            # Không tính lại phiếu đã gửi hoặc đã duyệt
            if Luong.objects.filter(
                tong_hop=cong,
                trang_thai__in=['Cho_giam_doc_duyet', 'Da_duyet']
            ).exists():
                continue

            # Tính lương từng nhân viên
            _tinh_phieu_luong(cong)
            so_phieu_da_tinh += 1

    return so_phieu_da_tinh



def _kiem_tra_phieu_luong_trong_ky(nam, thang):
    # Lấy các phiếu lương trong tháng
    phieu_luong = Luong.objects.filter(
        tong_hop__nam=nam,
        tong_hop__thang=thang
    )

    # Kiểm tra có phiếu lương hay chưa
    if not phieu_luong.exists():
        raise ValidationError('Chưa có bảng lương trong tháng.')

    # Đếm số bảng công đã chốt
    so_bang_cong = TongHopCong.objects.filter(
        nam=nam,
        thang=thang,
        chotbangcong__isnull=False
    ).count()

    # Kiểm tra số phiếu lương có đầy đủ không
    if phieu_luong.count() != so_bang_cong:
        raise ValidationError('Số phiếu lương không khớp bảng công đã chốt.')

    return phieu_luong



@transaction.atomic
def gui_bang_luong_cho_giam_doc(actor, nam, thang):
    if not co_vai_tro(actor, NHAN_SU):
        raise PermissionDenied('Chỉ Nhân sự được gửi bảng lương.')

    phieu_luong = _kiem_tra_phieu_luong_trong_ky(nam, thang)

    if phieu_luong.exclude(trang_thai='Cho_duyet').exists():
        raise ValidationError('Bảng lương chưa sẵn sàng để gửi.')

    return phieu_luong.update(trang_thai='Cho_giam_doc_duyet')


@transaction.atomic
def duyet_toan_bo_bang_luong(actor, nam, thang):
    if not co_vai_tro(actor, GIAM_DOC):
        raise PermissionDenied('Chỉ Giám đốc được duyệt bảng lương.')

    phieu_luong = _kiem_tra_phieu_luong_trong_ky(nam, thang)

    if phieu_luong.exclude(trang_thai='Cho_giam_doc_duyet').exists():
        raise ValidationError('Bảng lương chưa được Nhân sự gửi.')

    return phieu_luong.update(trang_thai='Da_duyet')
