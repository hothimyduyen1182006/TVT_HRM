from django.urls import path
from .views import bonus_list

app_name = 'bonuses'
urlpatterns = [path('', bonus_list, name='list')]
