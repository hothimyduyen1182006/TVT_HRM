from django.contrib import admin

from nhan_vien.admin_utils import CalendarLockedAdmin, ReadOnlyAdmin

from .models import ChamCong, ChotBangCong, KyCong, LichLamViec, NhatKyCong


@admin.register(KyCong)
class KyCongAdmin(admin.ModelAdmin):
    list_display = ('thang', 'nam', 'trang_thai', 'phien_ban')
    readonly_fields = ('trang_thai', 'phien_ban', 'ds_nhan_vien', 'nguoi_duyet', 'ngay_duyet')
    actions = None

    def has_change_permission(self, request, obj=None):
        if obj is not None:
            if obj.trang_thai != 'pending' or obj.employee_approvals.exists():
                return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LichLamViec)
class LichLamViecAdmin(CalendarLockedAdmin):
    list_display = ('ngay', 'loai_ngay', 'cong_chuan', 'ghi_chu')
    list_filter = ('loai_ngay',)
    date_hierarchy = 'ngay'


@admin.register(ChamCong)
class ChamCongAdmin(ReadOnlyAdmin):
    list_display = ('nhan_vien', 'ngay', 'trang_thai', 'so_gio_lam', 'tong_cong')


@admin.register(NhatKyCong)
class NhatKyCongAdmin(ReadOnlyAdmin):
    list_display = ('ngay_tao', 'nguoi_thuc_hien', 'hanh_dong', 'ly_do')


@admin.register(ChotBangCong)
class ChotBangCongAdmin(ReadOnlyAdmin):
    list_display = ('nhan_vien', 'ky_cong', 'nguoi_duyet', 'ngay_duyet')
