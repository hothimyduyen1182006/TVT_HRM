from django.urls import path
from . import views
from . import clock_views

app_name = 'bang_cong'
urlpatterns = [
    path('ca-nhan/', views.bang_cong_ca_nhan, name='ca-nhan'),
    path('cham-cong/', clock_views.cham_cong_hom_nay, name='cham-cong'),
    path('', views.danh_sach_bang_cong, name='danh-sach'),
    path('them/', views.sua_cham_cong, name='them'),
    path('nhan-vien/<int:employee_id>/', views.bang_cong_nhan_vien, name='cong-nhan-vien'),
    path('nhan-vien/<int:employee_id>/duyet/<int:period_id>/', views.duyet_bang_cong_nhan_vien, name='duyet-cong'),
    path('nhan-vien/<int:employee_id>/lich-su/', views.lich_su_dieu_chinh, name='lich-su'),
    path('nhan-vien/<int:employee_id>/xuat/', views.xuat_bang_cong, name='xuat'),
    path('<int:pk>/', views.chi_tiet_cham_cong, name='chi-tiet'),
    path('<int:pk>/sua/', views.sua_cham_cong, name='sua'),
    path('ky-cong/<int:pk>/', views.doi_trang_thai_ky_cong, name='doi-trang-thai'),
]
