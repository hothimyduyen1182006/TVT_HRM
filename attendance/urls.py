from django.urls import path
from . import views

app_name = 'attendance'
urlpatterns = [
    path('', views.record_list, name='list'),
    path('new/', views.edit, name='create'),
    path('employee/<int:employee_id>/', views.employee_month, name='employee-month'),
    path('employee/<int:employee_id>/approve/<int:period_id>/', views.approve_employee_view, name='employee-approve'),
    path('employee/<int:employee_id>/history/', views.history, name='history'),
    path('employee/<int:employee_id>/export/', views.export_month, name='export'),
    path('<int:pk>/', views.detail, name='detail'),
    path('<int:pk>/edit/', views.edit, name='edit'),
    path('period/<int:pk>/', views.transition, name='transition'),
]
