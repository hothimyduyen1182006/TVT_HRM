from django.urls import path
from .views import (
    bang_cong_ca_nhan, bang_cong_nhan_vien, cham_cong_hom_nay,
    chot_nhan_vien_da_chon, danh_sach_bang_cong,
)

app_name = 'bang_cong'
urlpatterns = [
    path('ca-nhan/', bang_cong_ca_nhan, name='ca-nhan'),
    path('cham-cong/', cham_cong_hom_nay, name='cham-cong'),
    path('', danh_sach_bang_cong, name='danh-sach'),
    path('nhan-vien/<int:employee_id>/', bang_cong_nhan_vien, name='cong-nhan-vien'),
    path('chot/<int:period_id>/', chot_nhan_vien_da_chon, name='chot-nhan-vien-da-chon'),
]
