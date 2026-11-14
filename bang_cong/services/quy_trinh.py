"""Lưu, duyệt, mở lại công; đồng bộ tổng hợp và lịch sử điều chỉnh."""

import calendar
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from nhan_vien.access import require_role, HR, DIRECTOR
from nhan_vien.models import Employee
from bang_cong.models import (
    KyCong, ChamCong, NhatKyCong, ChotBangCong, TongHopCong, LichSuDieuChinhCong,
)
from .tinh_toan import tinh_cong_ngay


def _ngay_cuoi_ky(ky_cong):
    return date(ky_cong.nam, ky_cong.thang, calendar.monthrange(ky_cong.nam, ky_cong.thang)[1])


def ky_cong_da_khoa(ky_cong, ma_nhan_vien, ngay_cong=None):
    if not ky_cong:
        return False
    if ky_cong.trang_thai == 'approved':
        return True
    ban_chot = ky_cong.employee_approvals.filter(nhan_vien_id=ma_nhan_vien).only('ngay_duyet').first()
    if not ban_chot:
        return False
    if ngay_cong is None:
        return not ChamCong.objects.filter(nhan_vien_id=ma_nhan_vien,
            ngay__year=ky_cong.nam, ngay__month=ky_cong.thang,
            ngay_cap_nhat__gt=ban_chot.ngay_duyet).exists()
    # Chốt công cá nhân chỉ khóa các bản ghi hoàn tất thuộc lần duyệt đó.
    return ChamCong.objects.filter(nhan_vien_id=ma_nhan_vien, ngay=ngay_cong).exclude(
        trang_thai='incomplete').filter(ngay_cap_nhat__lte=ban_chot.ngay_duyet).exists()


def cham_cong_da_khoa(ban_ghi):
    ky_cong = KyCong.objects.filter(nam=ban_ghi.ngay.year, thang=ban_ghi.ngay.month).first()
    return ky_cong_da_khoa(ky_cong, ban_ghi.nhan_vien_id, ban_ghi.ngay)


def _tinh_lai_cac_ban_ghi(ds_ban_ghi, ky_cong, nguoi_thuc_hien, ly_do):
    """Tính lại công và ghi lịch sử bằng cùng một luồng khi duyệt kỳ hoặc nhân viên."""
    for ban_ghi in ds_ban_ghi:
        du_lieu_cu = du_lieu_cham_cong(ban_ghi)
        tinh_cong_ngay(ban_ghi, ky_cong)
        ban_ghi.save()
        du_lieu_moi = du_lieu_cham_cong(ban_ghi)
        if du_lieu_cu != du_lieu_moi:
            nhat_ky = NhatKyCong.objects.create(nguoi_thuc_hien=nguoi_thuc_hien, hanh_dong='recalculate', ly_do=ly_do,
                du_lieu_cu=du_lieu_cu, du_lieu_moi=du_lieu_moi)
            ghi_lich_su_dieu_chinh(nhat_ky)


def du_lieu_cham_cong(ban_ghi):
    # Giữ khóa JSON lịch sử để đối chiếu phiếu lương và nhật ký cũ.
    cac_truong = {
        'pk': 'pk', 'employee_id': 'nhan_vien_id', 'date': 'ngay',
        'check_in': 'gio_vao', 'check_out': 'gio_ra', 'status': 'trang_thai',
        'work_hours': 'so_gio_lam', 'late_minutes': 'so_phut_tre',
        'actual_units': 'cong_thuc_te', 'paid_leave_units': 'cong_nghi_co_luong',
        'paid_units': 'tong_cong', 'overtime_hours': 'gio_tang_ca', 'note': 'ghi_chu',
    }
    return {khoa: str(getattr(ban_ghi, truong)) for khoa, truong in cac_truong.items()}


@transaction.atomic
def luu_cham_cong(nguoi_thuc_hien, ban_ghi, ly_do):
    require_role(nguoi_thuc_hien, HR, DIRECTOR)
    if not ly_do.strip():
        raise ValidationError('Cần lý do thay đổi.')
    ky_cong = KyCong.objects.select_for_update().get(nam=ban_ghi.ngay.year, thang=ban_ghi.ngay.month)
    if ky_cong_da_khoa(ky_cong, ban_ghi.nhan_vien_id, ban_ghi.ngay):
        raise ValidationError('Kỳ công đã duyệt, cần mở lại trước.')
    du_lieu_cu = {}
    if ban_ghi.pk:
        cu = ChamCong.objects.select_for_update().get(pk=ban_ghi.pk)
        if cu.nhan_vien_id != ban_ghi.nhan_vien_id or cu.ngay != ban_ghi.ngay:
            raise ValidationError('Không đổi nhân viên/ngày của bản ghi đã tạo.')
        du_lieu_cu = du_lieu_cham_cong(cu)
    ban_ghi.nguoi_cap_nhat = nguoi_thuc_hien
    tinh_cong_ngay(ban_ghi, ky_cong)
    ban_ghi.full_clean()
    ban_ghi.save()
    du_lieu_moi = du_lieu_cham_cong(ban_ghi)
    if not du_lieu_cu:
        NhatKyCong.objects.create(nguoi_thuc_hien=nguoi_thuc_hien, hanh_dong='create_record', ly_do=ly_do, du_lieu_cu={}, du_lieu_moi=du_lieu_moi)
    elif du_lieu_cu != du_lieu_moi:
        nhat_ky = NhatKyCong.objects.create(nguoi_thuc_hien=nguoi_thuc_hien, hanh_dong='edit_record', ly_do=ly_do, du_lieu_cu=du_lieu_cu, du_lieu_moi=du_lieu_moi)
        ghi_lich_su_dieu_chinh(nhat_ky)
    cap_nhat_tong_hop(ban_ghi.nhan_vien, ky_cong)
    return ban_ghi


@transaction.atomic
def xu_ly_trang_thai_ky_cong(nguoi_thuc_hien, ma_ky_cong, thao_tac, ly_do):
    require_role(nguoi_thuc_hien, DIRECTOR)
    ky_cong = KyCong.objects.select_for_update().get(pk=ma_ky_cong)
    if not ly_do.strip():
        raise ValidationError('Cần ghi lý do.')
    du_lieu_cu = {'period': ky_cong.pk, 'status': ky_cong.trang_thai, 'revision': ky_cong.phien_ban}
    if thao_tac == 'approve':
        if ky_cong.trang_thai != 'pending':
            raise ValidationError('Kỳ công phải đang chờ duyệt.')
        from .cham_cong import kiem_tra_lich_lam_viec
        lich_da_kiem_tra = kiem_tra_lich_lam_viec(ky_cong)
        ds_ban_ghi = ChamCong.objects.filter(ngay__year=ky_cong.nam, ngay__month=ky_cong.thang)
        ds_nhan_vien = Employee.objects.filter(is_active=True, hire_date__lte=_ngay_cuoi_ky(ky_cong))
        for nhan_vien in ds_nhan_vien:
            ngay_bat_buoc = {lich_ngay.ngay for lich_ngay in lich_da_kiem_tra
                        if lich_ngay.loai_ngay == 'work' and lich_ngay.ngay >= nhan_vien.hire_date}
            ngay_da_co = set(ds_ban_ghi.filter(nhan_vien=nhan_vien).exclude(trang_thai='incomplete').values_list('ngay', flat=True))
            if not set(ngay_bat_buoc).issubset(ngay_da_co):
                raise ValidationError(f'{nhan_vien}: còn ngày làm việc chưa kiểm tra.')
        _tinh_lai_cac_ban_ghi(ds_ban_ghi, ky_cong, nguoi_thuc_hien, ly_do)
        ky_cong.trang_thai = 'approved'
        ky_cong.ds_nhan_vien = list(ds_nhan_vien.values_list('pk', flat=True))
        for nhan_vien in ds_nhan_vien:
            ChotBangCong.objects.get_or_create(ky_cong=ky_cong, nhan_vien=nhan_vien, defaults={'nguoi_duyet': nguoi_thuc_hien})
        ky_cong.nguoi_duyet = nguoi_thuc_hien
        ky_cong.ngay_duyet = timezone.now()
    elif thao_tac == 'reopen':
        if ky_cong.trang_thai != 'approved':
            raise ValidationError('Chỉ mở lại kỳ đã duyệt.')
        from bang_luong.models import PayrollPeriod
        if PayrollPeriod.objects.filter(attendance_period=ky_cong).filter(
                Q(status__in=['approved', 'paid']) | Q(records__trang_thai__in=['approved', 'paid'])).exists():
            raise ValidationError('Cần mở lại bảng lương trước; lương đã chi trả không mở lại trực tiếp.')
        ky_cong.trang_thai = 'pending'
        ky_cong.phien_ban += 1
        ky_cong.nguoi_duyet = None
        ky_cong.ngay_duyet = None
        ky_cong.employee_approvals.all().delete()
    else:
        raise ValidationError('Thao tác không hợp lệ.')
    ky_cong.save()
    cap_nhat_tong_hop_ca_ky(ky_cong)
    NhatKyCong.objects.create(nguoi_thuc_hien=nguoi_thuc_hien, hanh_dong=thao_tac, ly_do=ly_do, du_lieu_cu=du_lieu_cu,
                                      du_lieu_moi={'period': ky_cong.pk, 'status': ky_cong.trang_thai, 'revision': ky_cong.phien_ban})
    if thao_tac == 'approve':
        from bang_luong.services.tinh_toan import cap_nhat_luong_nhan_vien
        for ma_nhan_vien in ky_cong.ds_nhan_vien:
            cap_nhat_luong_nhan_vien(nguoi_thuc_hien, ma_nhan_vien, ky_cong.nam, ky_cong.thang)


@transaction.atomic
def duyet_cong_nhan_vien(nguoi_thuc_hien, nhan_vien, ma_ky_cong):
    require_role(nguoi_thuc_hien, HR, DIRECTOR)
    ky_cong = KyCong.objects.select_for_update().get(pk=ma_ky_cong)
    if ky_cong_da_khoa(ky_cong, nhan_vien.pk):
        raise ValidationError('Bảng công nhân viên này đã được duyệt.')
    from .cham_cong import kiem_tra_lich_lam_viec
    lich_da_kiem_tra = kiem_tra_lich_lam_viec(ky_cong)
    ds_ban_ghi = ChamCong.objects.filter(nhan_vien=nhan_vien, ngay__year=ky_cong.nam, ngay__month=ky_cong.thang)
    ngay_bat_buoc = {lich_ngay.ngay for lich_ngay in lich_da_kiem_tra
                if lich_ngay.loai_ngay == 'work' and lich_ngay.ngay >= nhan_vien.hire_date}
    ngay_da_co = set(ds_ban_ghi.exclude(trang_thai='incomplete').values_list('ngay', flat=True))
    if not ds_ban_ghi.exists() or not ngay_bat_buoc.issubset(ngay_da_co) or ds_ban_ghi.filter(trang_thai='incomplete').exists():
        raise ValidationError('Bảng công nhân viên còn thiếu ngày hoặc có dữ liệu chưa kiểm tra.')
    _tinh_lai_cac_ban_ghi(ds_ban_ghi, ky_cong, nguoi_thuc_hien, 'Tính lại trước khi duyệt nhân viên')
    ban_chot = ky_cong.employee_approvals.filter(nhan_vien=nhan_vien).first()
    if ban_chot:
        ban_chot.nguoi_duyet = nguoi_thuc_hien
        ban_chot.ngay_duyet = timezone.now()
        ban_chot.save(update_fields=['nguoi_duyet', 'ngay_duyet'])
    else:
        ban_chot = ChotBangCong.objects.create(ky_cong=ky_cong, nhan_vien=nhan_vien, nguoi_duyet=nguoi_thuc_hien)
    NhatKyCong.objects.create(nguoi_thuc_hien=nguoi_thuc_hien, hanh_dong='approve_employee', ly_do='Duyệt công nhân viên từ trang chi tiết chấm công',
        du_lieu_cu={'approval_status': 'pending'}, du_lieu_moi={'employee_id': str(nhan_vien.pk),
            'date': f'{ky_cong.nam:04}-{ky_cong.thang:02}-01', 'approval_status': 'approved'})
    ds_ma_nhan_vien = set(Employee.objects.filter(is_active=True,
        hire_date__lte=_ngay_cuoi_ky(ky_cong)).values_list('pk', flat=True))
    ma_da_duyet_hop_le = set()
    for ban_chot_nhan_vien in ky_cong.employee_approvals.all():
        if not ChamCong.objects.filter(nhan_vien_id=ban_chot_nhan_vien.nhan_vien_id,
                ngay__year=ky_cong.nam, ngay__month=ky_cong.thang,
                ngay_cap_nhat__gt=ban_chot_nhan_vien.ngay_duyet).exists():
            ma_da_duyet_hop_le.add(ban_chot_nhan_vien.nhan_vien_id)
    if ds_ma_nhan_vien and ds_ma_nhan_vien.issubset(ma_da_duyet_hop_le):
        ky_cong.trang_thai = 'approved'
        ky_cong.ds_nhan_vien = sorted(ds_ma_nhan_vien)
        ky_cong.nguoi_duyet = nguoi_thuc_hien
        ky_cong.ngay_duyet = timezone.now()
        ky_cong.save()
        NhatKyCong.objects.create(nguoi_thuc_hien=nguoi_thuc_hien, hanh_dong='approve', ly_do='Tất cả nhân viên trong kỳ đã được duyệt riêng',
            du_lieu_cu={'period': ky_cong.pk, 'status': 'pending'}, du_lieu_moi={'period': ky_cong.pk, 'status': 'approved', 'revision': ky_cong.phien_ban})
    cap_nhat_tong_hop(nhan_vien, ky_cong)
    from bang_luong.services.tinh_toan import cap_nhat_luong_nhan_vien
    ban_chot.payroll_error = cap_nhat_luong_nhan_vien(nguoi_thuc_hien, nhan_vien.pk, ky_cong.nam, ky_cong.thang)
    return ban_chot


def du_lieu_tong_hop(nhan_vien, ky_cong):
    """Chuyển kết quả tổng hợp tháng thành các trường của bảng Tổng hợp công."""
    from .hien_thi import tong_hop_cong_thang

    dong = tong_hop_cong_thang(Employee.objects.filter(pk=nhan_vien.pk), ky_cong.nam, ky_cong.thang, ky_cong)[0]
    return {
        'thang': ky_cong.thang, 'nam': ky_cong.nam,
        'cong_chuan': dong['standard'] or 0, 'cong_thuc_te': dong['actual'],
        'cong_nghi_co_luong': dong['leave'], 'so_ngay_khong_phep': dong['absent'],
        'tong_cong': dong['paid'], 'so_gio_lam': dong['hours'],
        'gio_tang_ca': dong['ot'], 'so_lan_tre': dong['late_count'],
        'so_phut_tre': dong['late'], 'trang_thai': dong['state'],
    }


def tong_hop_dung_tinh_luong(nhan_vien, ky_cong):
    """Đọc bản tổng hợp còn khớp nguồn; dữ liệu cũ chưa đồng bộ chỉ tính trong bộ nhớ."""
    du_lieu = du_lieu_tong_hop(nhan_vien, ky_cong)
    da_luu = TongHopCong.objects.filter(nhan_vien=nhan_vien, ky_cong=ky_cong).first()
    if da_luu and all(getattr(da_luu, khoa) == gia_tri for khoa, gia_tri in du_lieu.items()):
        return da_luu
    return TongHopCong(nhan_vien=nhan_vien, ky_cong=ky_cong, **du_lieu)


@transaction.atomic
def cap_nhat_tong_hop(nhan_vien, ky_cong):
    """Cập nhật một bản tổng hợp và nối với bản chốt còn thiếu liên kết."""
    KyCong.objects.select_for_update().get(pk=ky_cong.pk)
    tong_hop, _ = TongHopCong.objects.update_or_create(
        nhan_vien=nhan_vien, ky_cong=ky_cong, defaults=du_lieu_tong_hop(nhan_vien, ky_cong),
    )
    ChotBangCong.objects.filter(
        nhan_vien=nhan_vien, ky_cong=ky_cong, tong_hop__isnull=True,
    ).update(tong_hop=tong_hop)
    return tong_hop


def cap_nhat_tong_hop_ca_ky(ky_cong):
    """Đồng bộ tổng hợp của các nhân viên đã vào làm trước cuối kỳ."""
    for nhan_vien in Employee.objects.filter(hire_date__lte=_ngay_cuoi_ky(ky_cong)):
        cap_nhat_tong_hop(nhan_vien, ky_cong)


def ghi_lich_su_dieu_chinh(nhat_ky):
    """Tách các trường đã thay đổi từ nhật ký gốc, không tạo dòng trùng."""
    from bang_cong.forms import CAC_TRUONG_DIEU_CHINH

    if not nhat_ky.du_lieu_cu or nhat_ky.hanh_dong not in ('edit_record', 'save_record', 'recalculate'):
        return
    try:
        ma_cham_cong = int(nhat_ky.du_lieu_moi.get('pk'))
    except (TypeError, ValueError):
        ma_cham_cong = None
    ma_cham_cong = ChamCong.objects.filter(pk=ma_cham_cong).values_list('pk', flat=True).first()
    for truong in CAC_TRUONG_DIEU_CHINH:
        cu, moi = nhat_ky.du_lieu_cu.get(truong, ''), nhat_ky.du_lieu_moi.get(truong, '')
        if cu != moi:
            LichSuDieuChinhCong.objects.get_or_create(nhat_ky=nhat_ky, truong_dieu_chinh=truong, defaults={
                'cham_cong_id': ma_cham_cong, 'nguoi_thuc_hien_id': nhat_ky.nguoi_thuc_hien_id,
                'gia_tri_cu': str(cu), 'gia_tri_moi': str(moi),
                'ly_do': nhat_ky.ly_do, 'ngay_dieu_chinh': nhat_ky.ngay_tao,
            })
