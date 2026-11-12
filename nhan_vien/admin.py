from django.contrib import admin
from .models import Department, Education, Employee, LaborContract, Position


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    readonly_fields = ('payroll_settings',)
    list_display = ('code', 'full_name', 'department', 'base_salary', 'is_active')
    list_filter = ('department', 'is_active')
    search_fields = ('code', 'full_name')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if change and set(form.changed_data) & {'base_salary', 'code', 'full_name', 'department'}:
            from bang_luong.models import PayrollPeriod
            from bang_luong.services.calculations import refresh_employee_payroll
            for period in PayrollPeriod.objects.filter(status='pending').select_related('attendance_period').order_by('attendance_period_id'):
                attendance = period.attendance_period
                error = refresh_employee_payroll(request.user, obj.pk, attendance.year, attendance.month)
                if error:
                    from django.contrib import messages
                    self.message_user(request, error, level=messages.WARNING)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    exclude = ('allows_overtime',)
    list_display = ('code', 'name', 'manager')


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('name', 'department', 'salary_coefficient')
    list_filter = ('department',)
    search_fields = ('name', 'department__name')


@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    list_display = ('code', 'employee', 'degree', 'school', 'graduation_year')
    search_fields = ('code', 'employee__full_name', 'degree', 'school')


@admin.register(LaborContract)
class LaborContractAdmin(admin.ModelAdmin):
    list_display = ('code', 'number', 'employee', 'contract_type', 'start_date', 'end_date', 'status')
    list_filter = ('status', 'contract_type')
    search_fields = ('code', 'number', 'employee__full_name')
