from django.urls import path

from . import views

app_name = 'warehouse'

urlpatterns = [
    path('', views.delivery_dashboard, name='dashboard'),
    path('export/', views.export_deliveries_excel, name='export'),
]
