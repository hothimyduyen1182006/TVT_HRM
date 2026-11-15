from django.contrib import admin

from nhan_vien.admin_utils import QuanTriKhoaTheoKyCong
from .models import LeaveDay, LeaveRequest


@admin.register(LeaveDay)
class LeaveDayAdmin(QuanTriKhoaTheoKyCong):
    list_display = ('employee', 'date', 'units', 'paid', 'approved')
    list_filter = ('approved', 'paid')


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('employee', 'Ngay_bat_dau', 'Ngay_ket_thuc', 'days_count', 'paid', 'Trang_thai', 'created_at')
    list_filter = ('Trang_thai', 'paid')
    search_fields = ('employee__ho_va_ten', 'employee__ma_ho_so', 'Ly_do')

    @admin.display(description='Số ngày nghỉ')
    def days_count(self, obj):
        return obj.days_count
