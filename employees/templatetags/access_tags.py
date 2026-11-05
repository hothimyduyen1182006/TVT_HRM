from django import template
from employees.access import has_role

register = template.Library()


@register.simple_tag
def role_allowed(user, *roles):
    return has_role(user, *roles)
