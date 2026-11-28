from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F

from bang_cong.models import TongHopCong
from bang_cong.services.cham_cong_service import cong_chuan_thang
from bang_luong.models import Luong
from bang_luong.services.can_cu_luong_service import LUONG_DONG_BAO_HIEM, lay_ty_le_bao_hiem
from nhan_vien.access import GIAM_DOC, NHAN_SU, co_vai_tro
from thuong.models import Thuong


def co_quyen_tinh_va_gui_luong(nguoi_dung):
    return co_vai_tro(nguoi_dung, NHAN_SU)


def co_quyen_ky_luong(nguoi_dung):
    return co_vai_tro(nguoi_dung, GIAM_DOC)


def _so_tien(value):
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def _lam_tron(value):
    return value.quantize(Decimal('1'), rounding=ROUND_HALF_UP)


def _bang_cong_da_chot(nam, thang):
    return TongHopCong.objects.filter(
        nam=nam, thang=thang, chotbangcong__isnull=False,
    )


def bang_cong_can_tinh_luong(nam, thang):
    return _bang_cong_da_chot(nam, thang).exclude(
        luong__trang_thai__in=['Cho_giam_doc_duyet', 'Da_duyet'],
    )


def them_cac_khoan_tong(bang_luong):
    return bang_luong.annotate(
        tong_thu_nhap=(
            F('luong_theo_cong') + F('luong_tang_ca')
            + F('phu_cap') + F('tong_tien_thuong')
        ),
        tong_khau_tru=F('khau_tru_bhxh') + F('thue_tncn') + F('khau_tru_khac'),
    )


def tinh_khau_tru_bao_hiem(nhan_vien):
    """Tính tổng bảo hiểm nhân viên phải đóng."""
    cai_dat = nhan_vien.thiet_lap_luong or {}
    ty_le_bao_hiem = lay_ty_le_bao_hiem(cai_dat)
    tong_ty_le = Decimal('0.105')
    if ty_le_bao_hiem:
        tong_ty_le = sum(_so_tien(ty_le_bao_hiem.get(ma)) for ma in ('BHXH', 'BHYT', 'BHTN'))
    tong_bao_hiem = LUONG_DONG_BAO_HIEM * tong_ty_le
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



def _tinh_phieu_luong(cong, thuong):
    nhan_vien = cong.nhan_vien
    cai_dat = nhan_vien.thiet_lap_luong or {}

    # Kiểm tra bảng thưởng trong kỳ trước khi tính lương.
    if thuong is not None and thuong.trang_thai != 'approved':
        raise ValidationError(
            f'Bảng thưởng của {nhan_vien.ho_va_ten} tháng {cong.thang:02}/{cong.nam} '
            'chưa được duyệt. Cần duyệt bảng thưởng trước khi tính lương.'
        )

    # 1. Tính lương theo công
    luong_co_ban = nhan_vien.luong_co_ban
    cong_chuan = cong_chuan_thang(cong.nam, cong.thang)
    luong_theo_cong = luong_co_ban * cong.tong_cong / cong_chuan

    # 2. Tính lương tăng ca
    gio_ot = cong.tong_gio_tang_ca
    don_gia_ot = _so_tien(cai_dat.get('luong_gio_tang_ca', 0))
    luong_tang_ca = gio_ot * don_gia_ot

    # 3. Phụ cấp và thưởng
    phu_cap = _so_tien(cai_dat.get('phu_cap_an_trua', 0))
    tong_thuong = thuong.tong_thuong if thuong else Decimal('0')

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
            'khau_tru_bhxh': tong_bao_hiem,
            'khau_tru_khac': 0,
            'thue_tncn': thue['thue_tncn'],
            'luong_thuc_linh': _lam_tron(thuc_linh),
            'trang_thai': 'Cho_duyet'
        }
    )


def tinh_bang_luong(actor, nam, thang):

    # Kiểm tra quyền nhân sự
    if not co_quyen_tinh_va_gui_luong(actor):
        raise PermissionDenied('Chỉ Quản lý nhân sự được tính lương.')

    # Lấy bảng công đã chốt
    bang_cong = _bang_cong_da_chot(nam, thang)

    if not bang_cong.exists():
        raise ValidationError('Chưa có bảng công được chốt.')

    with transaction.atomic():
        cong_can_tinh = list(bang_cong_can_tinh_luong(nam, thang).select_related('nhan_vien'))
        if not cong_can_tinh:
            return 0

        ma_nguoi_dung = set()
        thuong_theo_nguoi_dung = {
            thuong.nguoi_dung_id: thuong
            for thuong in Thuong.objects.filter(
                nam=nam, thang=thang, nguoi_dung_id__in=ma_nguoi_dung,
            ).select_related('nguoi_dung__employee')
        }
        for cong in cong_can_tinh:
            thuong = thuong_theo_nguoi_dung.get(cong.nhan_vien.nguoi_dung_id)
            _tinh_phieu_luong(cong, thuong)

    return len(cong_can_tinh)



def _kiem_tra_phieu_luong_trong_ky(nam, thang):
    # Lấy các phiếu lương trong tháng
    phieu_luong = Luong.objects.filter(
        tong_hop__nam=nam,
        tong_hop__thang=thang
    )

    # Kiểm tra có phiếu lương hay chưa
    if not phieu_luong.exists():
        raise ValidationError('Chưa có bảng lương trong tháng.')

    bang_cong_da_chot = _bang_cong_da_chot(nam, thang)
    if bang_cong_da_chot.filter(luong__isnull=True).exists():
        raise ValidationError('Có bảng công đã chốt chưa được tính lương.')
    if phieu_luong.filter(tong_hop__chotbangcong__isnull=True).exists():
        raise ValidationError('Có phiếu lương thuộc bảng công chưa chốt.')

    return phieu_luong



@transaction.atomic
def gui_bang_luong_cho_giam_doc(actor, nam, thang):
    if not co_quyen_tinh_va_gui_luong(actor):
        raise PermissionDenied('Chỉ Nhân sự được gửi bảng lương.')

    phieu_luong = _kiem_tra_phieu_luong_trong_ky(nam, thang)

    if phieu_luong.exclude(trang_thai='Cho_duyet').exists():
        raise ValidationError('Bảng lương chưa sẵn sàng để gửi.')

    return phieu_luong.update(trang_thai='Cho_giam_doc_duyet')


@transaction.atomic
def duyet_toan_bo_bang_luong(actor, nam, thang):
    if not co_quyen_ky_luong(actor):
        raise PermissionDenied('Chỉ Giám đốc được duyệt bảng lương.')

    phieu_luong = _kiem_tra_phieu_luong_trong_ky(nam, thang)

    if phieu_luong.exclude(trang_thai='Cho_giam_doc_duyet').exists():
        raise ValidationError('Bảng lương chưa được Nhân sự gửi.')

    return phieu_luong.update(trang_thai='Da_duyet')
