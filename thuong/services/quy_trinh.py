"""Lưu đề xuất, đồng bộ và xử lý duyệt thưởng."""
from decimal import Decimal

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from nhan_vien.models import NhanVien
from ..models import DeXuatThuong, Thuong
from .hien_thi import bang_thuong_trong_pham_vi
from .tinh_toan import tinh_thuong_tu_dong


@transaction.atomic
def dong_bo_thuong_tu_dong(nhan_vien, thang, nam):
    NhanVien.objects.select_for_update().get(pk=nhan_vien.pk)
    bang, _ = Thuong.objects.select_for_update().get_or_create(nguoi_dung=nhan_vien.nguoi_dung, thang=thang, nam=nam)
    if bang.trang_thai in ['pending', 'approved']:
        return bang
    cac_khoan, loi = tinh_thuong_tu_dong(nhan_vien, thang, nam)
    gia_tri = {'seniority': ('thuong_tham_nien', 'ly_do_tham_nien'),
               'attendance': ('thuong_chuyen_can', 'ly_do_chuyen_can')}
    thay_doi = False
    for loai, _, tien, ly_do in cac_khoan:
        cot_tien, cot_ly_do = gia_tri[loai]
        if getattr(bang, cot_tien) != tien or getattr(bang, cot_ly_do) != ly_do:
            setattr(bang, cot_tien, tien)
            setattr(bang, cot_ly_do, ly_do)
            thay_doi = True
    if loi and bang.ly_do_chuyen_can is not None:
        bang.thuong_chuyen_can, bang.ly_do_chuyen_can = Decimal(0), None
        thay_doi = True
    if thay_doi:
        luu_bang_thuong(bang)
    return bang


def luu_bang_thuong(bang):
    bang.tong_thuong = bang.thuong_chuyen_can + bang.thuong_tham_nien + bang.thuong_khac
    bang.full_clean()
    bang.save()


def gui_duyet_bang(bang):
    if bang.trang_thai not in ['draft', 'rejected'] or not bang.ly_do_chuyen_can or not bang.ly_do_tham_nien:
        raise ValidationError('Chỉ gửi bảng thưởng khi có đủ căn cứ thâm niên và chuyên cần.')
    bang.trang_thai = 'pending'
    bang.nguoi_duyet = bang.ngay_duyet = None
    bang.ly_do_tu_choi = ''
    luu_bang_thuong(bang)


def duyet_bang(bang, nguoi_dung, tu_choi=False, ly_do=''):
    if bang.trang_thai != 'pending':
        raise ValidationError('Chỉ xử lý bảng thưởng đang Chờ duyệt.')
    bang.trang_thai = 'rejected' if tu_choi else 'approved'
    bang.nguoi_duyet, bang.ngay_duyet = nguoi_dung, timezone.now()
    bang.ly_do_tu_choi = ly_do.strip() if tu_choi else ''
    luu_bang_thuong(bang)


def cap_nhat_thuong_khac(bang):
    bang.thuong_khac = bang.de_xuat.aggregate(tong=Sum('so_tien'))['tong'] or Decimal(0)
    bang.trang_thai, bang.ly_do_tu_choi = 'draft', ''
    bang.nguoi_duyet = bang.ngay_duyet = None
    luu_bang_thuong(bang)


@transaction.atomic
def luu_de_xuat(de_xuat):
    bang = Thuong.objects.select_for_update().get(pk=de_xuat.bang_thuong_id)
    if bang.trang_thai not in ['draft', 'rejected']:
        raise ValidationError('Chỉ sửa đề xuất khi bảng thưởng là Bản nháp hoặc Từ chối.')
    de_xuat.full_clean()
    de_xuat.save()
    cap_nhat_thuong_khac(bang)


@transaction.atomic
def xoa_de_xuat(de_xuat):
    bang = Thuong.objects.select_for_update().get(pk=de_xuat.bang_thuong_id)
    if bang.trang_thai not in ['draft', 'rejected']:
        raise ValidationError('Chỉ xóa đề xuất khi bảng thưởng là Bản nháp hoặc Từ chối.')
    de_xuat.delete()
    cap_nhat_thuong_khac(bang)


def cap_nhat_de_xuat_tu_form(de_xuat, du_lieu, nguoi_dung):
    for cot in ['ten', 'so_tien', 'ly_do']:
        setattr(de_xuat, cot, du_lieu[cot])
    de_xuat.nguoi_de_xuat = nguoi_dung
    de_xuat.thoi_gian_de_xuat = timezone.now()
    luu_de_xuat(de_xuat)


def ghi_lich_su(nguoi_dung, bang, noi_dung):
    LogEntry.objects.log_action(user_id=nguoi_dung.pk, content_type_id=ContentType.objects.get_for_model(Thuong).pk,
        object_id=str(bang.pk), object_repr=str(bang), action_flag=CHANGE, change_message=noi_dung)


def duyet_cac_bang(nguoi_dung, ds, nam, thang, thao_tac, ly_do, gui_duyet=False):
    if gui_duyet:
        noi_dung_lich_su = 'Gửi duyệt thưởng.'
    elif thao_tac == 'reject':
        noi_dung_lich_su = f'Từ chối thưởng. Lý do: {ly_do}'
    else:
        noi_dung_lich_su = 'Duyệt thưởng.'
    with transaction.atomic():
        cac_bang = list(bang_thuong_trong_pham_vi(nguoi_dung).select_for_update().filter(
            nguoi_dung__employee__pk__in=ds, nam=nam, thang=thang,
            trang_thai__in=['draft', 'rejected'] if gui_duyet else ['pending']))
        if not cac_bang:
            raise ValidationError('Không có bảng thưởng hợp lệ trong số nhân viên đã chọn.')
        for bang in cac_bang:
            if gui_duyet:
                gui_duyet_bang(bang)
            else:
                duyet_bang(bang, nguoi_dung, tu_choi=thao_tac == 'reject', ly_do=ly_do)
            ghi_lich_su(nguoi_dung, bang, noi_dung_lich_su)
    return cac_bang


@transaction.atomic
def tao_de_xuat_thuong(nguoi_dung, du_lieu):
    bang, _ = Thuong.objects.get_or_create(nguoi_dung=du_lieu['nhan_vien'].nguoi_dung, thang=du_lieu['thang'], nam=du_lieu['nam'])
    de_xuat = bang.de_xuat.filter(ten=du_lieu['ten']).first() or DeXuatThuong(bang_thuong=bang)
    cap_nhat_de_xuat_tu_form(de_xuat, du_lieu, nguoi_dung)
    return bang
