from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError

from nhan_vien.access import GIAM_DOC, NHAN_SU, co_vai_tro


LUONG_DONG_BAO_HIEM = Decimal('4730000')


def luu_thiet_lap_luong(nguoi_thuc_hien, nhan_vien, thiet_lap):
    """Kiểm tra và lưu thiết lập lương vào hồ sơ nhân viên."""
    if not co_vai_tro(nguoi_thuc_hien, NHAN_SU, GIAM_DOC):
        raise PermissionDenied('Chỉ Quản lý nhân sự hoặc Giám đốc được sửa thông tin này.')
    from nhan_vien.forms import BieuMauThietLapLuong

    du_lieu_bieu_mau = {
        ten_truong: thiet_lap[ten_truong]
        for ten_truong in BieuMauThietLapLuong.base_fields
        if ten_truong in thiet_lap
    }
    ty_le_bao_hiem = lay_ty_le_bao_hiem(thiet_lap)
    for ten_truong, ma_bao_hiem in BieuMauThietLapLuong.KHOA_TY_LE.items():
        du_lieu_bieu_mau[ten_truong] = ty_le_bao_hiem.get(ma_bao_hiem, 0)
    bieu_mau = BieuMauThietLapLuong(nhan_vien, data=du_lieu_bieu_mau)
    if not bieu_mau.is_valid():
        raise ValidationError(bieu_mau.errors.as_text())
    nhan_vien.thiet_lap_luong = chuan_hoa_du_lieu(bieu_mau.du_lieu_thiet_lap())
    nhan_vien.save(update_fields=['thiet_lap_luong'])
    return nhan_vien


def lay_ty_le_bao_hiem(thiet_lap):
    """Đọc tỷ lệ bảo hiểm từ thiết lập lương hiện tại hoặc dữ liệu cũ."""
    return thiet_lap.get('ty_le_bao_hiem') or thiet_lap.get('insurance_rates') or {}


def chuan_hoa_du_lieu(value):
    if isinstance(value, Decimal):
        return format(value.normalize(), 'f')
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: chuan_hoa_du_lieu(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [chuan_hoa_du_lieu(item) for item in value]
    return value
