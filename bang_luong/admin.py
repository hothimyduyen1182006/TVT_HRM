from django.contrib import admin
from nhan_vien.admin_utils import ReadOnlyAdmin
from .models import PayrollPeriod, Luong, PayrollAuditLog


@admin.register(PayrollPeriod)
class KyLuongAdmin(admin.ModelAdmin):
    list_display = ('attendance_period', 'status', 'approved_at', 'paid_at')
    readonly_fields = ('status', 'attendance_revision', 'approved_by', 'approved_at',
                       'paid_by', 'paid_at', 'payment_evidence')
    actions = None

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Luong)
class LuongAdmin(ReadOnlyAdmin):
    list_display = ('ma_nhan_vien', 'ten_nhan_vien', 'ky_luong', 'luong_thuc_linh')


@admin.register(PayrollAuditLog)
class NhatKyLuongAdmin(ReadOnlyAdmin):
    list_display = ('period', 'actor', 'created_at', 'action')
