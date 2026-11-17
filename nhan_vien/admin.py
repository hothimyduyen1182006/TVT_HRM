from django.contrib import admin
from .models import PhongBan, HocVan, NhanVien, HopDongLaoDong, ChucVu


@admin.register(NhanVien)
class NhanVienAdmin(admin.ModelAdmin):
    readonly_fields = ('thiet_lap_luong',)
    list_display = ('ma_ho_so', 'ho_va_ten', 'phong_ban', 'luong_co_ban', 'dang_hoat_dong')
    list_filter = ('phong_ban', 'dang_hoat_dong')
    search_fields = ('ma_ho_so', 'ho_va_ten')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change and set(form.changed_data) & {'luong_co_ban', 'ma_ho_so', 'ho_va_ten', 'phong_ban'}:
            from bang_luong.models import Luong
            from bang_luong.services.tinh_luong_service import cap_nhat_luong_nhan_vien
            months = Luong.objects.filter(trang_thai=Luong.CHO_DUYET).values_list(
                'tong_hop__nam', 'tong_hop__thang',
            ).distinct()
            for year, month in months:
                error = cap_nhat_luong_nhan_vien(request.user, obj.pk, year, month)
                if error:
                    from django.contrib import messages
                    self.message_user(request, error, level=messages.WARNING)


@admin.register(PhongBan)
class PhongBanAdmin(admin.ModelAdmin):
    exclude = ('cho_phep_tang_ca',)
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
