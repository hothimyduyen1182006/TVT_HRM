"""Tính công ngày và tăng ca; không tự lưu hoặc phê duyệt dữ liệu."""
import calendar
from datetime import date, datetime, time
from types import SimpleNamespace
from decimal import Decimal, ROUND_DOWN

from django.core.exceptions import ValidationError

from nghi_phep.models import NgayNghi
from bang_cong.models import ChamCong
from bang_cong.thang_lich import thang_lich, cac_thang_trong_nam

CHINH_SACH_OT = 'automatic-checkout-1700-v1'
KHONG = Decimal(0)


NGAY_LE_2026 = {
    date(2026, 1, 1): 'Tết Dương lịch',
    **{date(2026, 2, ngay): 'Tết Âm lịch' for ngay in range(16, 21)},
    date(2026, 4, 26): 'Giỗ Tổ Hùng Vương',
    date(2026, 4, 30): 'Ngày Chiến thắng',
    date(2026, 5, 1): 'Quốc tế Lao động',
    date(2026, 9, 1): 'Quốc khánh - ngày liền kề',
    date(2026, 9, 2): 'Quốc khánh',
    date(2026, 11, 24): 'Ngày Văn hóa Việt Nam',
}
NGHI_BU_2026 = {date(2026, 4, 27): 'Nghỉ bù ngày nghỉ tuần trùng Giỗ Tổ'}


def lich_du_kien(ngay):
    """Lịch TVT 2026; năm khác phải được cấu hình riêng."""
    if ngay.year != 2026:
        raise ValidationError('Chưa cấu hình lịch lễ cho năm này.')
    if ngay in NGAY_LE_2026:
        return 'holiday', Decimal(0), NGAY_LE_2026[ngay]
    if ngay in NGHI_BU_2026:
        return 'rest', Decimal(0), NGHI_BU_2026[ngay]
    if ngay.weekday() >= 5:
        return 'rest', Decimal(0), 'Nghỉ hằng tuần'
    return 'work', Decimal(1), ''


def lich_thang(nam, thang, ky_cong=None):
    """Lịch tháng được suy ra trực tiếp từ quy tắc đã cấu hình trong code."""
    ky_cong = ky_cong or thang_lich(nam, thang)
    if nam != 2026:
        return {}
    ket_qua = {}
    for so_ngay in range(1, calendar.monthrange(nam, thang)[1] + 1):
        ngay = date(nam, thang, so_ngay)
        loai, cong, ghi_chu = lich_du_kien(ngay)
        ket_qua[ngay] = SimpleNamespace(ngay=ngay, loai_ngay=loai,
                                       cong_chuan=Decimal(str(cong)), ghi_chu=ghi_chu)
    return ket_qua


def cong_chuan_thang(ky_cong):
    return sum((ngay.cong_chuan for ngay in lich_thang(
        ky_cong.nam, ky_cong.thang, ky_cong,
    ).values()), KHONG)


def tinh_so_gio(ngay, gio_bat_dau, gio_ket_thuc):
    """Đổi khoảng thời gian trong cùng ngày thành số giờ, giữ 4 số thập phân."""
    so_giay = max(0, int((
        datetime.combine(ngay, gio_ket_thuc) - datetime.combine(ngay, gio_bat_dau)
    ).total_seconds()))
    return (Decimal(so_giay) / Decimal(3600)).quantize(
        Decimal('0.0001'), rounding=ROUND_DOWN,
    )


def tinh_tang_ca_tu_dong(ban_ghi, ky_cong=None, lich_ngay=None):
    """Tính OT cho mọi phòng ban, không dùng các yêu cầu duyệt OT cũ."""
    # Giữ khóa kết quả để tương thích template và dữ liệu lương/lịch sử đã lưu.
    ket_qua = {
        'id': ban_ghi.pk, 'date': str(ban_ghi.ngay), 'start': '', 'end': '',
        'hours': KHONG, 'multiplier': KHONG, 'warnings': [], 'error': '',
    }
    if (ban_ghi.trang_thai != 'present' or not ban_ghi.gio_vao or not ban_ghi.gio_ra
            or ban_ghi.gio_ra <= ban_ghi.gio_vao or ban_ghi.ngay < ban_ghi.nhan_vien.ngay_vao_lam):
        return ket_qua

    ky_cong = ky_cong or thang_lich(ban_ghi.ngay.year, ban_ghi.ngay.month)
    lich_ngay = lich_ngay or lich_thang(ban_ghi.ngay.year, ban_ghi.ngay.month, ky_cong).get(ban_ghi.ngay)
    if not ky_cong or not lich_ngay:
        ket_qua['error'] = 'Thiếu cấu hình kỳ công hoặc lịch ngày để xác định OT.'
        return ket_qua

    gio_bat_dau = max(ban_ghi.gio_vao, time(17)) if lich_ngay.loai_ngay == 'work' else ban_ghi.gio_vao
    gio_ket_thuc = ban_ghi.gio_ra
    if gio_bat_dau >= gio_ket_thuc:
        return ket_qua

    so_gio = tinh_so_gio(ban_ghi.ngay, gio_bat_dau, gio_ket_thuc)
    if lich_ngay.loai_ngay != 'work':
        bat_dau_nghi = max(gio_bat_dau, ky_cong.bat_dau_nghi_trua)
        ket_thuc_nghi = min(gio_ket_thuc, ky_cong.ket_thuc_nghi_trua)
        if bat_dau_nghi < ket_thuc_nghi:
            so_gio -= tinh_so_gio(ban_ghi.ngay, bat_dau_nghi, ket_thuc_nghi)

    ket_qua.update(
        start=str(gio_bat_dau), end=str(gio_ket_thuc), hours=max(KHONG, so_gio),
        multiplier={'work': Decimal('1.5'), 'rest': Decimal(2), 'holiday': Decimal(3)}[lich_ngay.loai_ngay],
    )
    if so_gio and (gio_bat_dau < time(6) or gio_ket_thuc > time(22)):
        ket_qua['error'] = 'Có giờ ban đêm (22:00–06:00); chưa hỗ trợ công thức OT ban đêm. Cần đối soát trước khi tính lương.'
    gio_chuan_ngay = min(ky_cong.gio_chuan * lich_ngay.cong_chuan, ky_cong.gio_chuan)
    if (lich_ngay.loai_ngay == 'work' and so_gio > gio_chuan_ngay / 2) or so_gio + ban_ghi.so_gio_lam > 12:
        ket_qua['warnings'].append('Vượt giới hạn giờ làm thêm trong ngày; giữ nguyên giờ thực tế, cần kiểm tra tổ chức lao động.')
    return ket_qua


def tong_hop_tang_ca_tinh_luong(nhan_vien, nam, thang):
    """Lấy OT trong tháng và cảnh báo tổng giờ tăng ca theo tháng/năm."""
    ky_cong = thang_lich(nam, thang)
    lich_cua_thang = lich_thang(nam, thang, ky_cong)
    danh_sach = []
    for ban_ghi in ChamCong.objects.filter(
        nhan_vien=nhan_vien, ngay__year=nam, ngay__month=thang,
    ).select_related('nhan_vien').order_by('ngay'):
        tang_ca = tinh_tang_ca_tu_dong(ban_ghi, ky_cong, lich_cua_thang.get(ban_ghi.ngay))
        if tang_ca['error']:
            raise ValidationError(f"{ban_ghi.ngay}: {tang_ca['error']}")
        if tang_ca['hours']:
            danh_sach.append(tang_ca)

    tong_gio_thang = sum((tang_ca['hours'] for tang_ca in danh_sach), KHONG)
    tong_gio_nam = KHONG
    cac_ky_cong = {(ky.nam, ky.thang): ky for ky in cac_thang_trong_nam(nam)}
    lich_nam = {ngay: lich for ky in cac_ky_cong.values() for ngay, lich in lich_thang(nam, ky.thang, ky).items()}
    for ban_ghi in ChamCong.objects.filter(nhan_vien=nhan_vien, ngay__year=nam).select_related('nhan_vien'):
        tong_gio_nam += tinh_tang_ca_tu_dong(
            ban_ghi, cac_ky_cong.get((nam, ban_ghi.ngay.month)), lich_nam.get(ban_ghi.ngay),
        )['hours']
    if danh_sach and tong_gio_thang > 40:
        danh_sach[0]['warnings'].append('Vượt 40 giờ OT/tháng; không tự cắt giờ hoặc tiền đã làm.')
    if danh_sach and tong_gio_nam > 200:
        danh_sach[0]['warnings'].append('Vượt ngưỡng mặc định 200 giờ OT/năm; cần kiểm tra điều kiện ngoại lệ theo pháp luật.')
    return danh_sach


def ket_qua_cong_ngay(ban_ghi, ky_cong=None, lich_ngay=None, nghi_phep=None):
    """Tính trong bộ nhớ; không ghi công ngày vào database."""
    ky_cong = ky_cong or thang_lich(ban_ghi.ngay.year, ban_ghi.ngay.month)
    if not ky_cong:
        raise ValidationError('Chưa cấu hình tháng chấm công.')
    lich_ngay = lich_ngay or lich_thang(ban_ghi.ngay.year, ban_ghi.ngay.month, ky_cong).get(ban_ghi.ngay)
    if lich_ngay is None:
        raise ValidationError('Chưa cấu hình lịch cho ngày này.')
    ket_qua = {'hours': KHONG, 'actual': KHONG, 'leave': KHONG, 'late': 0}
    if ban_ghi.gio_vao and ban_ghi.gio_ra:
        thoi_diem = lambda gio: datetime.combine(ban_ghi.ngay, gio)
        bat_dau = max(thoi_diem(ban_ghi.gio_vao), thoi_diem(ky_cong.gio_bat_dau))
        ket_thuc = min(thoi_diem(ban_ghi.gio_ra), thoi_diem(ky_cong.gio_ket_thuc), thoi_diem(time(17)))
        so_giay = max(0, int((ket_thuc - bat_dau).total_seconds()))
        giay_nghi_trua = max(0, int((
            min(ket_thuc, thoi_diem(ky_cong.ket_thuc_nghi_trua))
            - max(bat_dau, thoi_diem(ky_cong.bat_dau_nghi_trua))
        ).total_seconds()))
        if lich_ngay.loai_ngay == 'work':
            ket_qua['hours'] = Decimal(max(0, so_giay - giay_nghi_trua)) / Decimal(3600)
            ket_qua['actual'] = min(lich_ngay.cong_chuan, ket_qua['hours'] / ky_cong.gio_chuan)
            # Ghi nhận phút trễ, làm tròn lên khi có giây; tiền phạt tính ở Bảng lương.
            giay_di_tre = max(0, int((thoi_diem(ban_ghi.gio_vao) - thoi_diem(ky_cong.gio_bat_dau)).total_seconds()))
            ket_qua['late'] = (giay_di_tre + 59) // 60

    if nghi_phep is None:
        nghi_phep = NgayNghi.objects.filter(
            don_nghi_phep__nhan_vien_id=ban_ghi.nhan_vien_id,
            don_nghi_phep__trang_thai='da_duyet',
            ngay=ban_ghi.ngay,
        ).select_related('don_nghi_phep').first()
    so_cong_nghi = Decimal('1.0000') if nghi_phep else KHONG
    ket_qua['leave'] = so_cong_nghi if nghi_phep and nghi_phep.huong_luong else KHONG
    if nghi_phep and ket_qua['actual'] + so_cong_nghi > lich_ngay.cong_chuan:
        raise ValidationError('Công thực tế và nghỉ phép vượt công chuẩn ngày; cần kiểm tra dữ liệu.')
    if ban_ghi.trang_thai == 'leave' and not nghi_phep:
        raise ValidationError('Chưa có nghỉ phép được duyệt cho ngày này.')
    for truong in ['hours', 'actual', 'leave']:
        ket_qua[truong] = ket_qua[truong].quantize(Decimal('0.0001'))
    return ket_qua


def nap_cong_ngay(ds_ban_ghi, ky_cong, lich=None):
    """Nạp nguồn nghỉ phép một lần cho cả tháng, dùng lại khi hiển thị/tính lương."""
    lich = lich if lich is not None else lich_thang(ky_cong.nam, ky_cong.thang, ky_cong)
    ds_phep = {
        (phep.don_nghi_phep.nhan_vien_id, phep.ngay): phep
        for phep in NgayNghi.objects.filter(
            don_nghi_phep__nhan_vien_id__in={r.nhan_vien_id for r in ds_ban_ghi},
            don_nghi_phep__trang_thai='da_duyet',
            ngay__year=ky_cong.nam,
            ngay__month=ky_cong.thang,
        ).select_related('don_nghi_phep')
    }
    for r in ds_ban_ghi:
        r._ket_qua_cong = ket_qua_cong_ngay(r, ky_cong, lich.get(r.ngay), ds_phep.get((r.nhan_vien_id, r.ngay), False))


def tinh_cong_ngay(ban_ghi, ky_cong):
    """Kiểm tra dữ liệu một lần trước khi tính giờ làm, phút trễ và tăng ca."""
    ban_ghi.full_clean()
    ket_qua = ket_qua_cong_ngay(ban_ghi, ky_cong)
    ban_ghi._ket_qua_cong = ket_qua
    ban_ghi.so_gio_lam = ket_qua['hours']
    ban_ghi.so_phut_tre = ket_qua['late']
    lich_ngay = lich_thang(ban_ghi.ngay.year, ban_ghi.ngay.month, ky_cong).get(ban_ghi.ngay)
    ban_ghi.so_gio_tang_ca = tinh_tang_ca_tu_dong(ban_ghi, ky_cong, lich_ngay)['hours']
    return ban_ghi


