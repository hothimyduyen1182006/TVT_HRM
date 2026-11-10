from django.contrib import admin
from employees.admin_utils import ReadOnlyAdmin
from .models import (PayrollPeriod, PayrollInput, PayrollAdjustment, PayrollRecord,
                     PayrollAuditLog, PayrollExportLog)


@admin.register(PayrollPeriod)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ('attendance_period', 'status', 'approved_at', 'paid_at')
    readonly_fields = ('status', 'attendance_revision', 'approved_by', 'approved_at',
                       'paid_by', 'paid_at', 'payment_evidence')
    actions = None

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class InputAdmin(admin.ModelAdmin):
    actions = None

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.period.attendance_revision = 0
        obj.period.save(update_fields=['attendance_revision'])
        PayrollAuditLog.objects.create(period=obj.period, actor=request.user, action='admin_input',
                                      reason='Cập nhật đầu vào; cần tính lại lương', snapshot=[])

    def has_change_permission(self, request, obj=None):
        return (obj is None or not obj.is_locked) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return (obj is None or not obj.is_locked) and super().has_delete_permission(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'period':
            kwargs['queryset'] = PayrollPeriod.objects.filter(status='pending')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(PayrollInput)
class PayrollInputAdmin(InputAdmin):
    list_display = ('employee', 'period', 'tax_method', 'verified')
    readonly_fields = ('tax_amount',)

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == 'tax_method':
            kwargs['choices'] = [choice for choice in db_field.choices if choice[0] != 'legacy']
        return super().formfield_for_choice_field(db_field, request, **kwargs)


@admin.register(PayrollAdjustment)
class AdjustmentAdmin(InputAdmin):
    list_display = ('employee', 'period', 'name', 'kind', 'amount', 'approved')


@admin.register(PayrollRecord)
class RecordAdmin(ReadOnlyAdmin):
    list_display = ('employee_code', 'employee_name', 'period', 'net_pay')


@admin.register(PayrollAuditLog)
class AuditAdmin(ReadOnlyAdmin):
    list_display = ('period', 'actor', 'created_at', 'action')


@admin.register(PayrollExportLog)
class ExportAdmin(ReadOnlyAdmin):
    list_display = ('actor', 'created_at', 'month', 'year', 'format')
