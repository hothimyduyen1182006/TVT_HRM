from django.contrib import admin
from .models import LeaveDay
from employees.admin_utils import CalendarLockedAdmin


@admin.register(LeaveDay)
class LeaveDayAdmin(CalendarLockedAdmin):
    list_display = ('employee', 'date', 'units', 'paid', 'approved')
    list_filter = ('approved', 'paid')
