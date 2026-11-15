from django.contrib import admin
from django.core.exceptions import PermissionDenied


class QuanTriChiDoc(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class QuanTriKhoaTheoKyCong(admin.ModelAdmin):
    """Không để trang quản trị vượt khóa kỳ công, kể cả xóa hàng loạt."""
    actions = None

    def ky_cong_da_khoa(self, doi_tuong):
        if doi_tuong is None:
            return False
        from bang_cong.models import ChotBangCong
        from bang_luong.models import PayrollPeriod as KyCong
        ngay = doi_tuong.date
        cac_ky_cong = KyCong.objects.filter(nam=ngay.year, thang=ngay.month)
        cac_ban_chot = ChotBangCong.objects.filter(tong_hop__ky_cong__in=cac_ky_cong)
        if hasattr(doi_tuong, 'employee_id'):
            cac_ban_chot = cac_ban_chot.filter(tong_hop__nhan_vien_id=doi_tuong.employee_id)
        return cac_ky_cong.filter(trang_thai='approved').exists() or cac_ban_chot.exists()

    def has_change_permission(self, request, obj=None):
        return not self.ky_cong_da_khoa(obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return not self.ky_cong_da_khoa(obj) and super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        if self.ky_cong_da_khoa(obj):
            raise PermissionDenied('Kỳ công đã khóa.')
        super().save_model(request, obj, form, change)
