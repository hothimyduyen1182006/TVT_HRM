from django import template
from nhan_vien.access import co_vai_tro

register = template.Library()


@register.simple_tag
def role_allowed(user, *roles):
    return co_vai_tro(user, *roles)
