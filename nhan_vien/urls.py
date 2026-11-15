from django.urls import path

from . import views


urlpatterns = [
    path('', views.danh_sach_nhan_vien, name='employees'),
    path('me/', views.ho_so_ca_nhan, name='personal_profile'),
    path('me/edit/', views.sua_ho_so_ca_nhan, name='personal_profile_edit'),
    path('new/', views.tao_nhan_vien, name='employee_create'),
    path('<int:ma_nhan_vien>/edit/', views.sua_nhan_vien, name='employee_edit'),
    path('<int:ma_nhan_vien>/bang_luong/<str:loai_thiet_lap>/new/', views.sua_thiet_lap_luong,
         name='employee_payroll_create'),
    path('<int:ma_nhan_vien>/bang_luong/<str:loai_thiet_lap>/<int:ma_ban_ghi>/', views.sua_thiet_lap_luong,
         name='employee_payroll_edit'),
    path('<int:ma_nhan_vien>/education/new/', views.sua_hoc_van, name='education_create'),
    path('<int:ma_nhan_vien>/education/<int:ma_ban_ghi>/edit/', views.sua_hoc_van, name='education_edit'),
    path('<int:ma_nhan_vien>/education/<int:ma_ban_ghi>/delete/', views.xoa_hoc_van, name='education_delete'),
    path('<int:ma_nhan_vien>/contracts/new/', views.sua_hop_dong_lao_dong, name='contract_create'),
    path('<int:ma_nhan_vien>/contracts/<int:ma_ban_ghi>/edit/', views.sua_hop_dong_lao_dong,
         name='contract_edit'),
    path('<int:ma_nhan_vien>/contracts/<int:ma_ban_ghi>/delete/', views.xoa_hop_dong_lao_dong,
         name='contract_delete'),
    path('<int:ma_nhan_vien>/', views.chi_tiet_nhan_vien, name='employee_detail'),
]
