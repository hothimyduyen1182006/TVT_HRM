from django import template
from nhan_vien.access import has_role

register = template.Library()


@register.simple_tag
def role_allowed(user, *roles):
    return has_role(user, *roles)
