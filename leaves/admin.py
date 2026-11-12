from django.contrib import admin

from employees.admin_utils import CalendarLockedAdmin
from .models import LeaveDay, LeaveRequest


@admin.register(LeaveDay)
class LeaveDayAdmin(CalendarLockedAdmin):
    list_display = ('employee', 'date', 'units', 'paid', 'approved')
    list_filter = ('approved', 'paid')


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('employee', 'start_date', 'end_date', 'units', 'paid', 'status', 'created_at')
    list_filter = ('status', 'paid')
    search_fields = ('employee__full_name', 'employee__code', 'reason')
