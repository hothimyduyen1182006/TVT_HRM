from django.urls import path

from .views import (
    danh_sach_thuong,
    xoa_de_xuat_thuong,
    chi_tiet_thuong,
    sua_de_xuat_thuong,
    xuat_bang_thuong,
    danh_sach_thuong_ca_nhan,
    de_xuat_thuong_khac,
    gui_duyet_thuong,
    xu_ly_duyet_thuong,
)

app_name = 'thuong'
urlpatterns = [
    path('', danh_sach_thuong, name='list'),
    path('my/', danh_sach_thuong_ca_nhan, name='personal'),
    path('propose/', de_xuat_thuong_khac, name='propose'),
    path('proposal/<str:bonus_id>/edit/', sua_de_xuat_thuong, name='proposal-edit'),
    path('proposal/<str:bonus_id>/delete/', xoa_de_xuat_thuong, name='proposal-delete'),
    path('detail/<int:nhan_vien_id>/<int:nam>/<int:thang>/', chi_tiet_thuong, name='detail'),
    path('<int:nam>/<int:thang>/submit/', gui_duyet_thuong, name='submit'),
    path('<int:nam>/<int:thang>/decision/', xu_ly_duyet_thuong, name='decision'),
    path('export/', xuat_bang_thuong, name='export'),
]
