from django.urls import path
from . import views
from . import clock_views

app_name = 'bang_cong'
urlpatterns = [
    path('ca-nhan/', views.bang_cong_ca_nhan, name='ca-nhan'),
    path('cham-cong/', clock_views.cham_cong_hom_nay, name='cham-cong'),
    path('', views.danh_sach_bang_cong, name='danh-sach'),
    path('them/', views.ghi_nhan_cham_cong, name='them'),
    path('nhan-vien/<int:employee_id>/', views.bang_cong_nhan_vien, name='cong-nhan-vien'),
    path('nhan-vien/<int:employee_id>/duyet/<int:period_id>/', views.duyet_bang_cong_nhan_vien, name='duyet-cong'),
    path('duyet-hang-loat/<int:period_id>/', views.duyet_cong_hang_loat, name='duyet-hang-loat'),
    path('ky-cong/<int:pk>/', views.doi_trang_thai_ky_cong, name='doi-trang-thai'),
]
