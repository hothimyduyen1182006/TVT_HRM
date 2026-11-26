from django.contrib import admin

from config.admin_utils import QuanTriChiDoc

from .models import ChamCong, ChotBangCong, TongHopCong


@admin.register(ChamCong)
class ChamCongAdmin(QuanTriChiDoc):
    list_display = ('nhan_vien', 'ngay', 'trang_thai', 'so_gio_lam', 'tong_cong')


@admin.register(ChotBangCong)
class ChotBangCongAdmin(QuanTriChiDoc):
    list_display = ('tong_hop_thang', 'nguoi_duyet', 'ngay_duyet')
    list_select_related = ('tong_hop__nhan_vien', 'nguoi_duyet')

    @admin.display(description='Tổng hợp công')
    def tong_hop_thang(self, obj):
        return str(obj.tong_hop)


@admin.register(TongHopCong)
class TongHopCongAdmin(QuanTriChiDoc):
    list_display = ('nhan_vien', 'thang', 'nam', 'cong_chuan', 'cong_thuc_te', 'tong_cong', 'trang_thai')
    list_filter = ('nam', 'thang', 'trang_thai')
