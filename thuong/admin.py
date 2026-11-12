from django.contrib import admin
from .models import Bonus


@admin.register(Bonus)
class BonusAdmin(admin.ModelAdmin):
    list_display = ('employee', 'name', 'month', 'year', 'amount', 'status')
    list_filter = ('status', 'year', 'month')
    readonly_fields = ('employee', 'month', 'year', 'name', 'bonus_type', 'reason', 'proposed_by',
                       'proposed_at', 'amount', 'status', 'rejection_reason', 'approved_by', 'approved_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
