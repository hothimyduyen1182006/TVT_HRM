from django.contrib import admin
from .models import PhongBan, HocVan, NhanVien, HopDongLaoDong, ChucVu


@admin.register(NhanVien)
class NhanVienAdmin(admin.ModelAdmin):
    readonly_fields = ('thiet_lap_luong',)
    list_display = ('ma_ho_so', 'ho_va_ten', 'phong_ban', 'luong_co_ban', 'dang_hoat_dong')
    list_filter = ('phong_ban', 'dang_hoat_dong')
    search_fields = ('ma_ho_so', 'ho_va_ten')


@admin.register(PhongBan)
class PhongBanAdmin(admin.ModelAdmin):
    list_display = ('ma_phong_ban', 'ten_phong_ban', 'truong_phong')


@admin.register(ChucVu)
class ChucVuAdmin(admin.ModelAdmin):
    list_display = ('ten_chuc_vu', 'phong_ban', 'he_so_luong_chuc_vu')
    list_filter = ('phong_ban',)
    search_fields = ('ten_chuc_vu', 'phong_ban__ten_phong_ban')


@admin.register(HocVan)
class HocVanAdmin(admin.ModelAdmin):
    list_display = ('ma_hoc_van', 'ho_so_ca_nhan', 'bang_cap', 'truong_hoc', 'nam_tot_nghiep')
    search_fields = ('ma_hoc_van', 'ho_so_ca_nhan__ho_va_ten', 'bang_cap', 'truong_hoc')


@admin.register(HopDongLaoDong)
class HopDongLaoDongAdmin(admin.ModelAdmin):
    list_display = ('ma_hop_dong', 'so_hop_dong', 'ho_so_ca_nhan', 'loai_hop_dong', 'ngay_bat_dau', 'ngay_ket_thuc', 'trang_thai')
    list_filter = ('trang_thai', 'loai_hop_dong')
    search_fields = ('ma_hop_dong', 'so_hop_dong', 'ho_so_ca_nhan__ho_va_ten')
