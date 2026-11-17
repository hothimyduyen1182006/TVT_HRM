from django.urls import path

from . import views

app_name = 'bang_luong'
urlpatterns = [
    path('', views.danh_sach_bang_luong, name='danh_sach'),
    path('ca-nhan/', views.luong_ca_nhan, name='ca_nhan'),
    path('tinh-luong/', views.tinh_luong, name='tinh_luong'),
    path('gui-giam-doc/', views.gui_bang_luong, name='gui_giam_doc'),
    path('ky-duyet/', views.ky_duyet_bang_luong, name='ky_duyet'),
    path('xuat/<str:fmt>/', views.xuat_bang_luong, name='xuat'),
    path('chi-tiet/<str:pk>/', views.chi_tiet_luong, name='chi_tiet'),
]
