from django.contrib import admin
from .models import Luong


class LuongAdmin(admin.ModelAdmin):
    list_display = (
        'ma_luong',
        'tong_hop',
        'luong_thuc_linh',
        'trang_thai',
    )

    list_filter = (
        'trang_thai',
        'tong_hop__nam',
        'tong_hop__thang',
    )

    search_fields = (
        'ma_luong',
        'tong_hop__nhan_vien__ma_ho_so',
        'tong_hop__nhan_vien__ho_va_ten',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Luong, LuongAdmin)
