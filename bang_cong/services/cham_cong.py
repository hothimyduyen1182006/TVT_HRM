"""Kiểm tra, kế thừa lịch làm việc và ghi nhận check-in/check-out."""

import calendar
from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from nhan_vien.models import Employee
from bang_cong.models import ChamCong, KyCong, LichLamViec, NhatKyCong
from .quy_trinh import ky_cong_da_khoa, cap_nhat_tong_hop
from .tinh_toan import tinh_cong_ngay


CAC_TRUONG_CA_LAM_VIEC = ('gio_bat_dau', 'bat_dau_nghi_trua', 'ket_thuc_nghi_trua', 'gio_ket_thuc', 'gio_chuan')


def _cau_hinh_ca(ky_cong):
    return {truong: getattr(ky_cong, truong) for truong in CAC_TRUONG_CA_LAM_VIEC}


def kiem_tra_lich_lam_viec(ky_cong):
    """Kiểm tra ca và toàn bộ lịch tháng, không phụ thuộc cờ xác nhận cũ."""
    ky_cong.full_clean(validate_unique=False, validate_constraints=False)
    ds_ngay = list(LichLamViec.objects.filter(ngay__year=ky_cong.nam, ngay__month=ky_cong.thang))
    if len(ds_ngay) != calendar.monthrange(ky_cong.nam, ky_cong.thang)[1]:
        raise ValidationError('Lịch chưa đủ tháng; cần cấu hình tất cả ngày trong tháng.')
    for ngay in ds_ngay:
        ngay.full_clean(validate_unique=False, validate_constraints=False)
    return ds_ngay


def mau_lich_tuan(ky_nguon):
    """Duyệt lịch nguồn một lần để xác định mẫu của từng thứ, bỏ ngày lễ."""
    lua_chon_theo_thu = {thu: set() for thu in range(7)}
    for lich in kiem_tra_lich_lam_viec(ky_nguon):
        if lich.loai_ngay != 'holiday':
            lua_chon_theo_thu[lich.ngay.weekday()].add((lich.loai_ngay, lich.cong_chuan))
    if any(len(lua_chon) != 1 for lua_chon in lua_chon_theo_thu.values()):
        raise ValidationError('Lịch nguồn có ngoại lệ theo tuần; HR cần cấu hình lịch tháng mới để tránh suy đoán sai.')
    return {thu: lua_chon.pop() for thu, lua_chon in lua_chon_theo_thu.items()}


def xem_lich_cham_cong(ngay):
    """Trả cấu hình có sẵn hoặc bản xem trước chưa lưu của tháng mới."""
    ky_cong = KyCong.objects.filter(nam=ngay.year, thang=ngay.month).first()
    lich_ngay = LichLamViec.objects.filter(ngay=ngay).first()
    ke_hoach = {'period': ky_cong, 'day': lich_ngay, 'source': None, 'weekly': {}, 'error': ''}
    if ky_cong:
        try:
            if lich_ngay:
                kiem_tra_lich_lam_viec(ky_cong)
            else:
                ky_cong.full_clean(validate_unique=False, validate_constraints=False)
        except ValidationError as loi:
            ke_hoach['error'] = ' '.join(loi.messages)
            return ke_hoach
    if ky_cong and lich_ngay:
        return ke_hoach
    if ky_cong and (ky_cong.trang_thai != 'pending' or ky_cong.employee_approvals.exists()):
        ke_hoach['error'] = 'Kỳ công đã có dữ liệu duyệt; không tự bổ sung hoặc thay đổi lịch đã khóa.'
        return ke_hoach
    ky_nguon = KyCong.objects.filter(
        Q(nam__lt=ngay.year) | Q(nam=ngay.year, thang__lt=ngay.month),
    ).order_by('-nam', '-thang').first()
    if not ky_nguon:
        ke_hoach['error'] = 'Chưa có ca và lịch làm việc để kế thừa. Vui lòng liên hệ HR.'
        return ke_hoach
    try:
        mau_tuan = mau_lich_tuan(ky_nguon)
    except ValidationError as loi:
        ke_hoach['error'] = ' '.join(loi.messages)
        return ke_hoach
    if not ky_cong:
        ky_cong = KyCong(nam=ngay.year, thang=ngay.month, **_cau_hinh_ca(ky_nguon))
    if not lich_ngay:
        loai_ngay, so_cong = mau_tuan[ngay.weekday()]
        lich_ngay = LichLamViec(ngay=ngay, loai_ngay=loai_ngay, cong_chuan=so_cong)
    ke_hoach.update(period=ky_cong, day=lich_ngay, source=ky_nguon, weekly=mau_tuan)
    return ke_hoach


@transaction.atomic
def dam_bao_lich_cham_cong(ngay, nguoi_thuc_hien):
    ke_hoach = xem_lich_cham_cong(ngay)
    if ke_hoach['error']:
        raise ValidationError(ke_hoach['error'])
    if ke_hoach['source']:
        KyCong.objects.select_for_update().get(pk=ke_hoach['source'].pk)
        ke_hoach = xem_lich_cham_cong(ngay)  # Kiểm tra lại sau khóa, không ghi từ bản xem trước cũ.
        if ke_hoach['error']:
            raise ValidationError(ke_hoach['error'])
    ban_xem_truoc = ke_hoach['period']
    if ban_xem_truoc.pk and ke_hoach['day'].pk:
        return ban_xem_truoc, ke_hoach['day']
    ky_cong, da_tao_ky = KyCong.objects.get_or_create(
        nam=ngay.year, thang=ngay.month, defaults=_cau_hinh_ca(ban_xem_truoc),
    )
    ky_cong = KyCong.objects.select_for_update().get(pk=ky_cong.pk)
    if ky_cong.trang_thai != 'pending' or ky_cong.employee_approvals.exists():
        raise ValidationError('Kỳ công đã thay đổi hoặc đã khóa. Vui lòng tải lại trang.')
    so_ngay_them = 0
    for so_ngay in range(1, calendar.monthrange(ngay.year, ngay.month)[1] + 1):
        gia_tri = date(ngay.year, ngay.month, so_ngay)
        loai_ngay, so_cong = ke_hoach['weekly'][gia_tri.weekday()]
        _, da_tao_ngay = LichLamViec.objects.get_or_create(ngay=gia_tri, defaults={
            'loai_ngay': loai_ngay, 'cong_chuan': so_cong,
            'ghi_chu': 'Nghỉ hằng tuần' if loai_ngay == 'rest' else '',
        })
        so_ngay_them += da_tao_ngay
    kiem_tra_lich_lam_viec(ky_cong)
    if da_tao_ky or so_ngay_them:
        NhatKyCong.objects.create(
            nguoi_thuc_hien=nguoi_thuc_hien, hanh_dong='auto_open_period',
            ly_do='Kế thừa ca và lịch tuần hợp lệ khi nhân viên chấm công', du_lieu_cu={},
            du_lieu_moi={'period': ky_cong.pk, 'source_period': ke_hoach['source'].pk,
                         'calendar_days_added': so_ngay_them},
        )
    return ky_cong, LichLamViec.objects.get(ngay=ngay)


@transaction.atomic
def ghi_nhan_cham_cong(nguoi_thuc_hien, thao_tac, ghi_chu=''):
    if not nguoi_thuc_hien.is_authenticated:
        raise PermissionDenied('Cần đăng nhập trước khi chấm công.')
    if thao_tac not in ('in', 'out'):
        raise ValidationError('Thao tác không hợp lệ.')

    hien_tai = timezone.localtime().replace(microsecond=0)
    hom_nay = hien_tai.date()
    gio_hien_tai = hien_tai.time()
    nhan_vien = (
        Employee.objects.select_for_update()
        .filter(user=nguoi_thuc_hien, is_active=True)
        .first()
    )
    if not nhan_vien:
        raise PermissionDenied('Tài khoản chưa liên kết nhân viên đang làm việc.')
    if hom_nay < nhan_vien.hire_date:
        raise ValidationError('Chưa đến ngày vào làm.')

    ky_cong, lich_ngay = dam_bao_lich_cham_cong(hom_nay, nguoi_thuc_hien)
    if ky_cong_da_khoa(ky_cong, nhan_vien.pk, hom_nay):
        raise ValidationError('Bảng công đã duyệt, không thể chấm công thêm.')
    if not lich_ngay or lich_ngay.loai_ngay != 'work':
        raise ValidationError('Hôm nay chưa có lịch làm việc thông thường được cấu hình.')
    ban_ghi = (
        ChamCong.objects.select_for_update()
        .filter(nhan_vien=nhan_vien, ngay=hom_nay)
        .first()
    )

    if thao_tac == 'in':
        if ban_ghi:
            raise ValidationError('Hôm nay đã có bản ghi chấm công. Không thể check-in lại.')
        ban_ghi = ChamCong(
            nhan_vien=nhan_vien, ngay=hom_nay,
            gio_vao=gio_hien_tai, trang_thai='incomplete',
        )
    else:  # Thao tác đã được kiểm tra ở đầu hàm, nên đây là check-out.
        if not ban_ghi or not ban_ghi.gio_vao:
            raise ValidationError('Bạn cần check-in trước.')
        if ban_ghi.gio_ra or ban_ghi.trang_thai != 'incomplete':
            raise ValidationError('Bản ghi đã kết thúc hoặc cần nhân sự kiểm tra.')
        if gio_hien_tai <= ban_ghi.gio_vao:
            raise ValidationError('Giờ check-out phải sau giờ check-in.')
        if len(ghi_chu) > 2000:
            raise ValidationError('Ghi chú tối đa 2000 ký tự.')
        # Dùng lại nhân viên đã lấy, tránh truy vấn khóa ngoại khi tính công.
        ban_ghi.nhan_vien = nhan_vien
        ban_ghi.gio_ra = gio_hien_tai
        ban_ghi.trang_thai = 'present'
        ban_ghi.ghi_chu = ghi_chu.strip()
        tinh_cong_ngay(ban_ghi, ky_cong)

    ban_ghi.nguoi_cap_nhat = nguoi_thuc_hien
    ban_ghi.full_clean()
    ban_ghi.save()
    cap_nhat_tong_hop(nhan_vien, ky_cong)
    return ban_ghi
