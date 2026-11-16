from django.contrib import admin
from .models import DeXuatThuong, Thuong


class ChiDocAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Thuong)
class ThuongAdmin(ChiDocAdmin):
    list_display = ('ma_thuong', 'nguoi_dung', 'thang', 'nam', 'tong_thuong', 'trang_thai')
    list_filter = ('trang_thai', 'nam', 'thang')


@admin.register(DeXuatThuong)
class DeXuatThuongAdmin(ChiDocAdmin):
    list_display = ('ten', 'bang_thuong', 'so_tien', 'nguoi_de_xuat', 'thoi_gian_de_xuat')
