from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError

from nhan_vien.access import GIAM_DOC, NHAN_SU, co_vai_tro


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


def luu_thiet_lap_luong(actor, nhan_vien, settings):
    """Giữ điểm tích hợp hồ sơ nhân viên; không tự gán tỷ lệ mặc định."""
    if not co_vai_tro(actor, NHAN_SU, GIAM_DOC):
        raise PermissionDenied('Chỉ Quản lý nhân sự hoặc Giám đốc được sửa thông tin này.')
    from nhan_vien.forms import BieuMauThietLapLuong

    payload = {
        f'salary-{field}': settings[key]
        for field, key in BieuMauThietLapLuong.KHOA_CAU_HINH.items()
        if key in settings
    }
    for field, key in BieuMauThietLapLuong.KHOA_TY_LE.items():
        payload[f'salary-{field}'] = Decimal(str(settings.get('insurance_rates', {}).get(key, 0))) * 100
    form = BieuMauThietLapLuong(nhan_vien, data=payload)
    if not form.is_valid():
        raise ValidationError(form.errors.as_text())
    nhan_vien.thiet_lap_luong = chuan_hoa_du_lieu(form.du_lieu_thiet_lap())
    nhan_vien.save(update_fields=['thiet_lap_luong'])
    return nhan_vien
