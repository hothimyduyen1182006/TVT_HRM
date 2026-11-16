from django.contrib import admin
from nhan_vien.admin_utils import QuanTriChiDoc
from .models import Luong


@admin.register(Luong)
class LuongAdmin(QuanTriChiDoc):
    list_display = ('ma_luong', 'tong_hop', 'luong_thuc_linh', 'trang_thai')
