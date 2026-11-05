from django.contrib import admin
from django.utils import timezone
from .models import Bonus


@admin.register(Bonus)
class BonusAdmin(admin.ModelAdmin):
    list_display = ('employee', 'name', 'month', 'year', 'amount', 'status')
    list_filter = ('status', 'year', 'month')
    readonly_fields = ('approved_by', 'approved_at')

    def save_model(self, request, obj, form, change):
        if obj.status == 'approved' and (not change or 'status' in form.changed_data):
            obj.approved_by = request.user
            obj.approved_at = timezone.now()
        if obj.status != 'approved':
            obj.approved_by = None
            obj.approved_at = None
        super().save_model(request, obj, form, change)
