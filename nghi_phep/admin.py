from django.contrib import admin

from nhan_vien.admin_utils import ReadOnlyAdmin

from .models import DonNghiPhep, NgayNghi


@admin.register(DonNghiPhep)
class DonNghiPhepAdmin(admin.ModelAdmin):
    list_display = (
        'nhan_vien', 'ngay_bat_dau', 'ngay_ket_thuc', 'loai_nghi',
        'trang_thai', 'ngay_tao',
    )
    list_filter = ('loai_nghi', 'trang_thai')
    search_fields = ('nhan_vien__full_name', 'nhan_vien__code', 'ly_do')


@admin.register(NgayNghi)
class NgayNghiAdmin(ReadOnlyAdmin):
    list_display = ('don_nghi_phep', 'ngay', 'nhan_vien', 'huong_luong')
    list_filter = ('don_nghi_phep__loai_nghi', 'don_nghi_phep__trang_thai')
