from django.contrib import admin

from nhan_vien.admin_utils import CalendarLockedAdmin
from .models import LeaveDay, LeaveRequest


@admin.register(LeaveDay)
class LeaveDayAdmin(CalendarLockedAdmin):
    list_display = ('employee', 'date', 'units', 'paid', 'approved')
    list_filter = ('approved', 'paid')


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('employee', 'Ngay_bat_dau', 'Ngay_ket_thuc', 'days_count', 'paid', 'Trang_thai', 'created_at')
    list_filter = ('Trang_thai', 'paid')
    search_fields = ('employee__full_name', 'employee__code', 'Ly_do')

    @admin.display(description='Số ngày nghỉ')
    def days_count(self, obj):
        return obj.days_count
