"""Tính công ngày và tăng ca; không tự lưu hoặc phê duyệt dữ liệu."""
from datetime import datetime, time
from decimal import Decimal, ROUND_DOWN

from django.core.exceptions import ValidationError

from nghi_phep.models import LeaveDay
from bang_cong.models import LichLamViec, KyCong, ChamCong

CHINH_SACH_OT = 'automatic-checkout-1700-v1'
KHONG = Decimal(0)


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
            or ban_ghi.gio_ra <= ban_ghi.gio_vao or ban_ghi.ngay < ban_ghi.nhan_vien.hire_date):
        return ket_qua

    ky_cong = ky_cong or KyCong.objects.filter(
        nam=ban_ghi.ngay.year, thang=ban_ghi.ngay.month,
    ).first()
    lich_ngay = lich_ngay or LichLamViec.objects.filter(ngay=ban_ghi.ngay).first()
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
    ky_cong = KyCong.objects.filter(nam=nam, thang=thang).first()
    lich_thang = {
        lich.ngay: lich
        for lich in LichLamViec.objects.filter(ngay__year=nam, ngay__month=thang)
    }
    danh_sach = []
    for ban_ghi in ChamCong.objects.filter(
        nhan_vien=nhan_vien, ngay__year=nam, ngay__month=thang,
    ).select_related('nhan_vien').order_by('ngay'):
        tang_ca = tinh_tang_ca_tu_dong(ban_ghi, ky_cong, lich_thang.get(ban_ghi.ngay))
        if tang_ca['error']:
            raise ValidationError(f"{ban_ghi.ngay}: {tang_ca['error']}")
        if tang_ca['hours']:
            danh_sach.append(tang_ca)

    tong_gio_thang = sum((tang_ca['hours'] for tang_ca in danh_sach), KHONG)
    tong_gio_nam = KHONG
    cac_ky_cong = {(ky.nam, ky.thang): ky for ky in KyCong.objects.filter(nam=nam)}
    lich_nam = {lich.ngay: lich for lich in LichLamViec.objects.filter(ngay__year=nam)}
    for ban_ghi in ChamCong.objects.filter(nhan_vien=nhan_vien, ngay__year=nam).select_related('nhan_vien'):
        tong_gio_nam += tinh_tang_ca_tu_dong(
            ban_ghi, cac_ky_cong.get((nam, ban_ghi.ngay.month)), lich_nam.get(ban_ghi.ngay),
        )['hours']
    if danh_sach and tong_gio_thang > 40:
        danh_sach[0]['warnings'].append('Vượt 40 giờ OT/tháng; không tự cắt giờ hoặc tiền đã làm.')
    if danh_sach and tong_gio_nam > 200:
        danh_sach[0]['warnings'].append('Vượt ngưỡng mặc định 200 giờ OT/năm; cần kiểm tra điều kiện ngoại lệ theo pháp luật.')
    return danh_sach


def tinh_cong_ngay(ban_ghi, ky_cong):
    """Tính giờ làm trong ca, phút trễ, công hưởng lương và OT của một ngày."""
    ban_ghi.full_clean()
    lich_ngay = LichLamViec.objects.filter(ngay=ban_ghi.ngay).first()
    if lich_ngay is None:
        raise ValidationError('Chưa cấu hình lịch cho ngày này.')
    ban_ghi.so_gio_lam = Decimal(0)
    ban_ghi.cong_thuc_te = Decimal(0)
    ban_ghi.so_phut_tre = 0
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
            ban_ghi.so_gio_lam = Decimal(max(0, so_giay - giay_nghi_trua)) / Decimal(3600)
            ban_ghi.cong_thuc_te = min(lich_ngay.cong_chuan, ban_ghi.so_gio_lam / ky_cong.gio_chuan)
            # Ghi nhận phút trễ, làm tròn lên khi có giây; tiền phạt tính ở Bảng lương.
            giay_di_tre = max(0, int((thoi_diem(ban_ghi.gio_vao) - thoi_diem(ky_cong.gio_bat_dau)).total_seconds()))
            ban_ghi.so_phut_tre = (giay_di_tre + 59) // 60

    nghi_phep = LeaveDay.objects.filter(employee=ban_ghi.nhan_vien, date=ban_ghi.ngay, approved=True).first()
    ban_ghi.cong_nghi_co_luong = nghi_phep.units if nghi_phep and nghi_phep.paid else Decimal(0)
    if nghi_phep and ban_ghi.cong_thuc_te + nghi_phep.units > lich_ngay.cong_chuan:
        raise ValidationError('Công thực tế và nghỉ phép vượt công chuẩn ngày; cần kiểm tra dữ liệu.')
    ban_ghi.tong_cong = ban_ghi.cong_thuc_te + ban_ghi.cong_nghi_co_luong
    if ban_ghi.trang_thai == 'leave' and not nghi_phep:
        raise ValidationError('Chưa có nghỉ phép được duyệt cho ngày này.')
    for truong in ['so_gio_lam', 'cong_thuc_te', 'cong_nghi_co_luong', 'tong_cong']:
        setattr(ban_ghi, truong, getattr(ban_ghi, truong).quantize(Decimal('0.0001')))
    ban_ghi.so_gio_tang_ca = tinh_tang_ca_tu_dong(ban_ghi, ky_cong, lich_ngay)['hours']
    return ban_ghi
