from django.contrib import admin
from django.core.exceptions import PermissionDenied


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CalendarLockedAdmin(admin.ModelAdmin):
    """Không để trang quản trị vượt khóa kỳ công, kể cả xóa hàng loạt."""
    actions = None

    def locked(self, obj):
        if obj is None:
            return False
        from bang_cong.models import AttendancePeriod, EmployeeAttendanceApproval
        periods = AttendancePeriod.objects.filter(year=obj.date.year, month=obj.date.month)
        approvals = EmployeeAttendanceApproval.objects.filter(period__in=periods)
        if hasattr(obj, 'employee_id'):
            approvals = approvals.filter(employee_id=obj.employee_id)
        return periods.filter(status='approved').exists() or approvals.exists()

    def has_change_permission(self, request, obj=None):
        return not self.locked(obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return not self.locked(obj) and super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        if self.locked(obj):
            raise PermissionDenied('Kỳ công đã khóa.')
        super().save_model(request, obj, form, change)
