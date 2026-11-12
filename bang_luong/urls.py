from django.urls import path
from . import views

app_name = 'bang_luong'
urlpatterns = [
    path('', views.record_list, name='list'),
    path('personal/', views.personal, name='personal'),
    path('inputs/', views.inputs, name='inputs'),
    path('inputs/<str:kind>/new/', views.edit_input, name='input-create'),
    path('inputs/<str:kind>/<int:pk>/', views.edit_input, name='input-edit'),
    path('<int:pk>/', views.detail, name='detail'),
    path('<int:pk>/approve/', views.approve_employee_payroll, name='employee-approve'),
    path('period/<int:pk>/', views.transition, name='transition'),
    path('export/<str:fmt>/', views.export, name='export'),
]
