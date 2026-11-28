"""Tính công ngày và tăng ca; không tự lưu hoặc chốt dữ liệu."""
from datetime import datetime, time
from decimal import Decimal, ROUND_DOWN

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from bang_cong.models import ChamCong
from bang_cong.services.chot_bang_cong_service import ky_cong_da_khoa
from nghi_phep.models import NgayNghi
from nhan_vien.models import NhanVien

CHINH_SACH_OT = 'automatic-checkout-1700-v1'
KHONG = Decimal(0)
GIO_BAT_DAU = time(8)
BAT_DAU_NGHI_TRUA = time(12)
KET_THUC_NGHI_TRUA = time(13)
GIO_KET_THUC = time(17)
GIO_CHUAN = Decimal(8)
CONG_CHUAN_THANG = Decimal('24.0000')


def cham_cong_da_khoa(ban_ghi):
    """Kiểm tra bản ghi công có thuộc kỳ đã chốt hay không."""
    return ky_cong_da_khoa(
        ban_ghi.ngay.year, ban_ghi.ngay.month,
        ban_ghi.nhan_vien_id,
    )


def du_lieu_cham_cong(ban_ghi):
    """Chuyển bản ghi công thành dữ liệu dạng chuỗi dùng cho lịch sử."""
    cac_truong = {
        'pk': 'pk', 'employee_id': 'nhan_vien_id', 'date': 'ngay',
        'check_in': 'gio_vao', 'check_out': 'gio_ra', 'status': 'trang_thai',
        'work_hours': 'so_gio_lam', 'late_minutes': 'so_phut_tre',
        'actual_units': 'cong_thuc_te', 'paid_leave_units': 'cong_nghi_co_luong',
        'paid_units': 'tong_cong', 'overtime_hours': 'gio_tang_ca',
    }
    return {khoa: str(getattr(ban_ghi, truong)) for khoa, truong in cac_truong.items()}


def cong_chuan_thang(nam, thang):
    """Trả về công chuẩn cố định của mọi tháng."""
    return CONG_CHUAN_THANG


def tinh_so_gio(ngay, gio_bat_dau, gio_ket_thuc):
    """Đổi khoảng thời gian trong cùng ngày thành số giờ, giữ 4 số thập phân."""
    so_giay = max(0, int((
        datetime.combine(ngay, gio_ket_thuc) - datetime.combine(ngay, gio_bat_dau)
    ).total_seconds()))
    return (Decimal(so_giay) / Decimal(3600)).quantize(
        Decimal('0.0001'), rounding=ROUND_DOWN,
    )


def tinh_phut_di_tre(ngay, gio_vao):
    """Tính số phút đi trễ; có giây lẻ thì làm tròn lên một phút."""
    if not gio_vao:
        return 0

    gio_vao = datetime.combine(ngay, gio_vao)
    gio_bat_dau = datetime.combine(ngay, GIO_BAT_DAU)
    giay_di_tre = max(0, int((gio_vao - gio_bat_dau).total_seconds()))
    return (giay_di_tre + 59) // 60


def tinh_tang_ca_tu_dong(ban_ghi):
    """Tính giờ tăng ca sau giờ kết thúc ca, không phân biệt loại ngày.

    Giữ khóa kết quả để tương thích template và dữ liệu lương/lịch sử đã lưu.
    """
    ket_qua = {
        'id': ban_ghi.pk, 'date': str(ban_ghi.ngay), 'start': '', 'end': '',
        'hours': KHONG, 'multiplier': KHONG, 'warnings': [], 'error': '',
    }
    if (ban_ghi.trang_thai != 'present' or not ban_ghi.gio_vao or not ban_ghi.gio_ra
            or ban_ghi.gio_ra <= ban_ghi.gio_vao or ban_ghi.ngay < ban_ghi.nhan_vien.ngay_vao_lam):
        return ket_qua

    gio_bat_dau = max(ban_ghi.gio_vao, GIO_KET_THUC)
    gio_ket_thuc = ban_ghi.gio_ra
    if gio_bat_dau >= gio_ket_thuc:
        return ket_qua

    so_gio = tinh_so_gio(ban_ghi.ngay, gio_bat_dau, gio_ket_thuc)
    ket_qua.update(
        start=str(gio_bat_dau), end=str(gio_ket_thuc), hours=max(KHONG, so_gio),
        multiplier=Decimal('1.5'),
    )
    if so_gio and (gio_bat_dau < time(6) or gio_ket_thuc > time(22)):
        ket_qua['error'] = 'Có giờ ban đêm (22:00–06:00); chưa hỗ trợ công thức OT ban đêm. Cần đối soát trước khi tính lương.'
    if so_gio > GIO_CHUAN / 2 or so_gio + ban_ghi.so_gio_lam > 12:
        ket_qua['warnings'].append('Vượt giới hạn giờ làm thêm trong ngày; giữ nguyên giờ thực tế, cần kiểm tra tổ chức lao động.')
    return ket_qua


def tong_hop_tang_ca_tinh_luong(nhan_vien, nam, thang):
    """Lấy giờ tăng ca trong tháng và cảnh báo nếu vượt 40 giờ."""
    danh_sach = []
    for ban_ghi in ChamCong.objects.filter(
        nhan_vien=nhan_vien, ngay__year=nam, ngay__month=thang,
    ).select_related('nhan_vien').order_by('ngay'):
        tang_ca = tinh_tang_ca_tu_dong(ban_ghi)
        if tang_ca['error']:
            raise ValidationError(f"{ban_ghi.ngay}: {tang_ca['error']}")
        if tang_ca['hours']:
            danh_sach.append(tang_ca)

    tong_gio_thang = sum((tang_ca['hours'] for tang_ca in danh_sach), KHONG)
    if danh_sach and tong_gio_thang > 40:
        danh_sach[0]['warnings'].append('Vượt 40 giờ OT/tháng; không tự cắt giờ hoặc tiền đã làm.')
    return danh_sach


def ket_qua_cong_ngay(ban_ghi, nghi_phep=None):
    """Tính trong bộ nhớ; không ghi công ngày vào database.

    Tính trễ ngay khi có giờ vào, kể cả khi nhân viên chưa kết thúc ca.
    """
    ket_qua = {'hours': KHONG, 'actual': KHONG, 'leave': KHONG, 'late': 0}
    if ban_ghi.gio_vao and ban_ghi.gio_ra:
        thoi_diem = lambda gio: datetime.combine(ban_ghi.ngay, gio)
        bat_dau = max(thoi_diem(ban_ghi.gio_vao), thoi_diem(GIO_BAT_DAU))
        ket_thuc = min(thoi_diem(ban_ghi.gio_ra), thoi_diem(GIO_KET_THUC))
        so_giay = max(0, int((ket_thuc - bat_dau).total_seconds()))
        giay_nghi_trua = max(0, int((
            min(ket_thuc, thoi_diem(KET_THUC_NGHI_TRUA))
            - max(bat_dau, thoi_diem(BAT_DAU_NGHI_TRUA))
        ).total_seconds()))
        ket_qua['hours'] = Decimal(max(0, so_giay - giay_nghi_trua)) / Decimal(3600)
        ket_qua['actual'] = min(Decimal(1), ket_qua['hours'] / GIO_CHUAN)

    if ban_ghi.gio_vao:
        ket_qua['late'] = tinh_phut_di_tre(ban_ghi.ngay, ban_ghi.gio_vao)

    if nghi_phep is None:
        nghi_phep = NgayNghi.objects.filter(
            don_nghi_phep__nhan_vien_id=ban_ghi.nhan_vien_id,
            don_nghi_phep__trang_thai='da_duyet',
            ngay=ban_ghi.ngay,
        ).select_related('don_nghi_phep').first()
    so_cong_nghi = Decimal('1.0000') if nghi_phep else KHONG
    if nghi_phep and nghi_phep.don_nghi_phep.huong_luong:
        ket_qua['leave'] = so_cong_nghi
    else:
        ket_qua['leave'] = KHONG
    if nghi_phep and ket_qua['actual'] + so_cong_nghi > 1:
        raise ValidationError('Công thực tế và nghỉ phép vượt công chuẩn ngày; cần kiểm tra dữ liệu.')
    if ban_ghi.trang_thai == 'leave' and not nghi_phep:
        raise ValidationError('Chưa có nghỉ phép được duyệt cho ngày này.')
    for truong in ['hours', 'actual', 'leave']:
        ket_qua[truong] = ket_qua[truong].quantize(Decimal('0.0001'))
    return ket_qua


def nap_cong_ngay(ds_ban_ghi, nam, thang):
    """Nạp nghỉ phép đã duyệt một lần cho tháng và tính công của từng bản ghi."""
    ds_phep = {
        (phep.don_nghi_phep.nhan_vien_id, phep.ngay): phep
        for phep in NgayNghi.objects.filter(
            don_nghi_phep__nhan_vien_id__in={r.nhan_vien_id for r in ds_ban_ghi},
            don_nghi_phep__trang_thai='da_duyet',
            ngay__year=nam,
            ngay__month=thang,
        ).select_related('don_nghi_phep')
    }
    for r in ds_ban_ghi:
        r._ket_qua_cong = ket_qua_cong_ngay(
            r, ds_phep.get((r.nhan_vien_id, r.ngay), False),
        )


def tinh_cong_ngay(ban_ghi):
    """Kiểm tra dữ liệu một lần trước khi tính giờ làm, phút trễ và tăng ca."""
    ban_ghi.full_clean()
    ket_qua = ket_qua_cong_ngay(ban_ghi)
    ban_ghi._ket_qua_cong = ket_qua
    ban_ghi.so_gio_lam = ket_qua['hours']
    ban_ghi.so_phut_tre = ket_qua['late']
    ban_ghi.so_gio_tang_ca = tinh_tang_ca_tu_dong(ban_ghi)['hours']
    return ban_ghi


@transaction.atomic
def ghi_nhan_cham_cong(nguoi_dung, thao_tac):
    from bang_cong.services.tong_hop_service import cap_nhat_tong_hop
    """Ghi nhận thao tác vào ca hoặc kết thúc ca của nhân viên đang đăng nhập."""
    if not nguoi_dung.is_authenticated:
        raise PermissionDenied('Cần đăng nhập trước khi chấm công.')
    if thao_tac not in ('in', 'out'):
        raise ValidationError('Thao tác không hợp lệ.')

    hien_tai = timezone.localtime().replace(microsecond=0)
    hom_nay = hien_tai.date()
    gio_hien_tai = hien_tai.time()

    nhan_vien = (
        NhanVien.objects.select_for_update()
        .filter(nguoi_dung=nguoi_dung, dang_hoat_dong=True)
        .first()
    )
    if not nhan_vien:
        raise PermissionDenied('Tài khoản chưa liên kết với nhân viên đang làm việc.')

    nam, thang = hom_nay.year, hom_nay.month
    if hom_nay < nhan_vien.ngay_vao_lam:
        raise ValidationError('Chưa đến ngày bắt đầu làm việc của nhân viên.')
    if ky_cong_da_khoa(nam, thang, nhan_vien.pk):
        raise ValidationError('Bảng công đã chốt, không thể chấm công thêm.')
    ban_ghi = (
        ChamCong.objects.select_for_update()
        .filter(nhan_vien=nhan_vien, ngay=hom_nay)
        .first()
    )

    if thao_tac == 'in':
        if ban_ghi:
            raise ValidationError('Hôm nay đã có bản ghi chấm công. Không thể vào ca lại.')

        ban_ghi = ChamCong(
            nhan_vien=nhan_vien,
            ngay=hom_nay,
            gio_vao=gio_hien_tai,
            so_phut_tre=tinh_phut_di_tre(hom_nay, gio_hien_tai),
            trang_thai='incomplete',
        )
        ban_ghi.full_clean()
    else:
        if not ban_ghi or not ban_ghi.gio_vao:
            raise ValidationError('Bạn cần vào ca trước.')
        if ban_ghi.gio_ra or ban_ghi.trang_thai != 'incomplete':
            raise ValidationError('Bản ghi đã kết thúc hoặc cần nhân sự kiểm tra.')

        ban_ghi.nhan_vien = nhan_vien
        ban_ghi.gio_ra = gio_hien_tai
        ban_ghi.trang_thai = 'present'
        tinh_cong_ngay(ban_ghi)

    ban_ghi.save()
    cap_nhat_tong_hop(nhan_vien, nam, thang)
    return ban_ghi


ghi_nhan_thao_tac_cham_cong = ghi_nhan_cham_cong
