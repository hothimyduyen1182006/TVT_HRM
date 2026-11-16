from django.urls import path

from . import views


app_name = 'nghi_phep'

urlpatterns = [
    path('', views.danh_sach_don_nghi, name='list'),
    path('<int:ma_don>/', views.chi_tiet_don_nghi, name='detail'),
    path('<int:ma_don>/huy/', views.huy_don_nghi, name='huy'),
    path('<int:ma_don>/evidence/', views.tai_minh_chung, name='evidence'),
    path('<int:ma_don>/attach-evidence/', views.bo_sung_minh_chung, name='attach_evidence'),
    path('<int:ma_don>/<str:thao_tac>/', views.xu_ly_don_nghi, name='review'),
]
