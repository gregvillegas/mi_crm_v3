from django.urls import path

from . import views

app_name = 'warehouse'

urlpatterns = [
    path('', views.delivery_dashboard, name='dashboard'),
    path('history/', views.delivery_history, name='history'),
    path('new/', views.delivery_create, name='create'),
    path('<int:pk>/edit/', views.delivery_update, name='update'),
    path('export/', views.export_deliveries_excel, name='export'),
]
