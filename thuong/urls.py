from django.urls import path

from .views import (
    bonus_list,
    calculate_period,
    delete_proposal,
    detail,
    edit_rejected_proposal,
    export,
    personal_list,
    propose,
    submit_period,
    decision_period,
)

app_name = 'thuong'
urlpatterns = [
    path('', bonus_list, name='list'),
    path('my/', personal_list, name='personal'),
    path('propose/', propose, name='propose'),
    path('proposal/<int:bonus_id>/edit/', edit_rejected_proposal, name='proposal-edit'),
    path('proposal/<int:bonus_id>/delete/', delete_proposal, name='proposal-delete'),
    path('calculate/', calculate_period, name='calculate'),
    path('detail/<int:employee_id>/<int:year>/<int:month>/', detail, name='detail'),
    path('<int:year>/<int:month>/submit/', submit_period, name='submit'),
    path('<int:year>/<int:month>/decision/', decision_period, name='decision'),
    path('export/', export, name='export'),
]
