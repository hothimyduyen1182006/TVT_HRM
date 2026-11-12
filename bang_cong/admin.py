from django.contrib import admin
from nhan_vien.admin_utils import ReadOnlyAdmin, CalendarLockedAdmin
from .models import AttendancePeriod, AttendanceRecord, WorkCalendarDay, OvertimeApproval, AttendanceAuditLog
from .models import EmployeeAttendanceApproval


@admin.register(AttendancePeriod)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ('month', 'year', 'status', 'policy_confirmed', 'revision')
    readonly_fields = ('status', 'revision', 'employee_ids', 'approved_by', 'approved_at')
    actions = None

    def has_change_permission(self, request, obj=None):
        return (obj is None or (obj.status == 'pending' and not obj.employee_approvals.exists())) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WorkCalendarDay)
class CalendarAdmin(CalendarLockedAdmin):
    list_display = ('date', 'kind', 'expected_units', 'name')
    list_filter = ('kind',)
    date_hierarchy = 'date'


@admin.register(OvertimeApproval)
class OvertimeAdmin(ReadOnlyAdmin):
    list_display = ('employee', 'date', 'hours', 'multiplier', 'approved')
    readonly_fields = ('approved_by', 'approved_at')


@admin.register(AttendanceRecord)
class RecordAdmin(ReadOnlyAdmin):
    list_display = ('employee', 'date', 'status', 'work_hours', 'paid_units')


@admin.register(AttendanceAuditLog)
class AuditAdmin(ReadOnlyAdmin):
    list_display = ('created_at', 'actor', 'action', 'reason')


@admin.register(EmployeeAttendanceApproval)
class EmployeeApprovalAdmin(ReadOnlyAdmin):
    list_display = ('employee', 'period', 'approved_by', 'approved_at')
