from django.urls import path
from . import views

app_name = 'bang_luong'
urlpatterns = [
    path('', views.danh_sach_bang_luong, name='list'),
    path('personal/', views.luong_ca_nhan, name='personal'),
    path('inputs/', views.thiet_lap_luong, name='inputs'),
    path('inputs/<str:kind>/new/', views.chuyen_den_thiet_lap_nhan_vien, name='input-create'),
    path('inputs/<str:kind>/<int:pk>/', views.chuyen_den_thiet_lap_nhan_vien, name='input-edit'),
    path('<int:pk>/', views.chi_tiet_luong, name='detail'),
    path('<int:pk>/approve/', views.duyet_luong_nhan_vien, name='employee-approve'),
    path('period/<int:pk>/', views.doi_trang_thai_ky_luong, name='transition'),
    path('export/<str:fmt>/', views.xuat_bang_luong, name='export'),
]
