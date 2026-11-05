from django.urls import path
from . import views

app_name = 'leaves'
urlpatterns = [
    path('', views.leave_list, name='list'),
    path('<int:pk>/', views.leave_detail, name='detail'),
    path('<int:pk>/evidence/', views.leave_evidence, name='evidence'),
    path('<int:pk>/<str:action>/', views.review_leave, name='review'),
]
