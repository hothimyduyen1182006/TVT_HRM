from django.contrib import admin

from nhan_vien.admin_utils import QuanTriChiDoc

from .models import ChamCong, ChotBangCong, LichSuDieuChinhCong


@admin.register(ChamCong)
class ChamCongAdmin(QuanTriChiDoc):
    list_display = ('nhan_vien', 'ngay', 'trang_thai', 'so_gio_lam', 'tong_cong')


@admin.register(LichSuDieuChinhCong)
class LichSuDieuChinhCongAdmin(QuanTriChiDoc):
    list_display = ('ngay_dieu_chinh', 'nhan_vien', 'ngay_cong', 'truong_dieu_chinh', 'nguoi_thuc_hien')


@admin.register(ChotBangCong)
class ChotBangCongAdmin(QuanTriChiDoc):
    list_display = ('nhan_vien', 'nam', 'thang', 'nguoi_duyet', 'ngay_duyet')
