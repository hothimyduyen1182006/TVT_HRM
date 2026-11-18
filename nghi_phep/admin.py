from django.contrib import admin

from config.admin_utils import QuanTriChiDoc

from .models import DonNghiPhep, NgayNghi


@admin.register(DonNghiPhep)
class DonNghiPhepAdmin(admin.ModelAdmin):
    list_display = (
        'nhan_vien', 'ngay_bat_dau', 'ngay_ket_thuc', 'loai_nghi',
        'trang_thai', 'ngay_tao',
    )
    list_filter = ('loai_nghi', 'trang_thai')
    search_fields = ('nhan_vien__ho_va_ten', 'nhan_vien__ma_ho_so', 'ly_do')


@admin.register(NgayNghi)
class NgayNghiAdmin(QuanTriChiDoc):
    list_display = ('don_nghi_phep', 'ngay', 'nhan_vien', 'huong_luong')
    list_filter = ('don_nghi_phep__loai_nghi', 'don_nghi_phep__trang_thai')

    @admin.display(description='Nhân viên')
    def nhan_vien(self, obj):
        return obj.don_nghi_phep.nhan_vien

    @admin.display(description='Hưởng lương')
    def huong_luong(self, obj):
        return obj.don_nghi_phep.huong_luong
