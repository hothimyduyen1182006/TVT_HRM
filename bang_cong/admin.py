from django.contrib import admin
from nhan_vien.admin_utils import ReadOnlyAdmin, CalendarLockedAdmin
from .models import KyCong, ChamCong, LichLamViec, NhatKyCong
from .models import ChotBangCong


@admin.register(KyCong)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ('thang', 'nam', 'trang_thai', 'phien_ban')
    readonly_fields = ('trang_thai', 'phien_ban', 'ds_nhan_vien', 'nguoi_duyet', 'ngay_duyet')
    actions = None

    def has_change_permission(self, request, obj=None):
        return (obj is None or (obj.trang_thai == 'pending' and not obj.employee_approvals.exists())) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LichLamViec)
class CalendarAdmin(CalendarLockedAdmin):
    list_display = ('ngay', 'loai_ngay', 'cong_chuan', 'ghi_chu')
    list_filter = ('loai_ngay',)
    date_hierarchy = 'ngay'


@admin.register(ChamCong)
class RecordAdmin(ReadOnlyAdmin):
    list_display = ('nhan_vien', 'ngay', 'trang_thai', 'so_gio_lam', 'tong_cong')


@admin.register(NhatKyCong)
class AuditAdmin(ReadOnlyAdmin):
    list_display = ('ngay_tao', 'nguoi_thuc_hien', 'hanh_dong', 'ly_do')


@admin.register(ChotBangCong)
class EmployeeApprovalAdmin(ReadOnlyAdmin):
    list_display = ('nhan_vien', 'ky_cong', 'nguoi_duyet', 'ngay_duyet')
