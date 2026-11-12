from django.urls import path

from .views import (
    bonus_list,
    calculate_period,
    decision,
    detail,
    export,
    personal_list,
    propose,
    submit,
)

app_name = 'thuong'
urlpatterns = [
    path('', bonus_list, name='list'),
    path('my/', personal_list, name='personal'),
    path('propose/', propose, name='propose'),
    path('calculate/', calculate_period, name='calculate'),
    path('detail/<int:employee_id>/<int:year>/<int:month>/', detail, name='detail'),
    path('<int:employee_id>/<int:year>/<int:month>/submit/', submit, name='submit'),
    path('<int:employee_id>/<int:year>/<int:month>/decision/', decision, name='decision'),
    path('export/', export, name='export'),
]
