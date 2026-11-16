from django.contrib import admin

from nhan_vien.admin_utils import QuanTriChiDoc

from .models import ChamCong, ChotBangCong


@admin.register(ChamCong)
class ChamCongAdmin(QuanTriChiDoc):
    list_display = ('nhan_vien', 'ngay', 'trang_thai', 'so_gio_lam', 'tong_cong')


@admin.register(ChotBangCong)
class ChotBangCongAdmin(QuanTriChiDoc):
    list_display = ('tong_hop', 'nguoi_duyet', 'ngay_duyet')
