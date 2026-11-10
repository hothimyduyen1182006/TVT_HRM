from django.contrib import admin
from .models import Department, Education, Employee, LaborContract, Position


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('code', 'full_name', 'department', 'base_salary', 'is_active')
    list_filter = ('department', 'is_active')
    search_fields = ('code', 'full_name')


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'manager', 'allows_overtime')


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
