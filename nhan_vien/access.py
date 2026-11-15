from django.core.exceptions import PermissionDenied

from .models import NhanVien


NHAN_SU = 'Nhân sự'
GIAM_DOC = 'Giám đốc'
TRUONG_PHONG = 'Trưởng phòng'


def co_vai_tro(nguoi_dung, *vai_tro):
    return nguoi_dung.is_authenticated and (
        nguoi_dung.is_superuser or nguoi_dung.groups.filter(name__in=vai_tro).exists()
    )


def yeu_cau_vai_tro(nguoi_dung, *vai_tro):
    if not co_vai_tro(nguoi_dung, *vai_tro):
        raise PermissionDenied('Bạn không có quyền thực hiện thao tác này.')


def nhan_vien_duoc_hien_thi(nguoi_dung):
    danh_sach_nhan_vien = NhanVien.objects.select_related('phong_ban', 'nguoi_dung')
    if co_vai_tro(nguoi_dung, NHAN_SU, GIAM_DOC):
        return danh_sach_nhan_vien
    if co_vai_tro(nguoi_dung, TRUONG_PHONG):
        return danh_sach_nhan_vien.filter(phong_ban__truong_phong__nguoi_dung=nguoi_dung)
    return danh_sach_nhan_vien.filter(nguoi_dung=nguoi_dung)
