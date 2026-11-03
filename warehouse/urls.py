from django.urls import path

from . import views

app_name = 'warehouse'

urlpatterns = [
    path('', views.delivery_dashboard, name='dashboard'),
    path('history/', views.delivery_history, name='history'),
    path('backlog-reasons/', views.backlog_reason_list, name='backlog_reason_list'),
    path(
        'backlog-reasons/new/',
        views.backlog_reason_create,
        name='backlog_reason_create',
    ),
    path(
        'backlog-reasons/<int:pk>/edit/',
        views.backlog_reason_update,
        name='backlog_reason_update',
    ),
    path('new/', views.delivery_create, name='create'),
    path('<int:pk>/timeline/', views.delivery_timeline, name='timeline'),
    path('<int:pk>/edit/', views.delivery_update, name='update'),
    path('<int:pk>/update-status/', views.delivery_update_status, name='update_status'),
    path('export/', views.export_deliveries_excel, name='export'),
]
