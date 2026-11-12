from django.core.exceptions import PermissionDenied

from .models import Employee


HR = 'Nhân sự'
DIRECTOR = 'Giám đốc'
MANAGER = 'Trưởng phòng'


def has_role(user, *roles):
    return user.is_authenticated and (user.is_superuser or user.groups.filter(name__in=roles).exists())


def require_role(user, *roles):
    if not has_role(user, *roles):
        raise PermissionDenied('Bạn không có quyền thực hiện thao tác này.')


def visible_employees(user):
    employees = Employee.objects.select_related('department', 'user')
    if has_role(user, HR, DIRECTOR):
        return employees
    if has_role(user, MANAGER):
        return employees.filter(department__manager__user=user)
    return employees.filter(user=user)
