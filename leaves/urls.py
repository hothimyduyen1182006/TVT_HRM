from django.urls import path
from .views import leave_list

app_name = 'leaves'
urlpatterns = [path('', leave_list, name='list')]
