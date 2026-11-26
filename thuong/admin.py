from django.contrib import admin
from .models import DeXuatThuong, Thuong


@admin.register(Thuong)
class ThuongAdmin(admin.ModelAdmin):
    list_display = ('ma_thuong', 'nguoi_dung', 'thang', 'nam', 'tong_thuong', 'trang_thai')
    list_filter = ('trang_thai', 'nam', 'thang')


@admin.register(DeXuatThuong)
class DeXuatThuongAdmin(admin.ModelAdmin):
    list_display = ('ten', 'bang_thuong', 'so_tien', 'nguoi_de_xuat', 'thoi_gian_de_xuat')
