from django.urls import path
from . import views

urlpatterns = [
    path('add-salesperson/', views.create_salesperson, name='create_salesperson'),
    path('manage/', views.user_management, name='user_management'),
    path('profile/', views.profile_view, name='profile'),
    path('create/', views.create_user, name='create_user'),
    path('edit/<int:user_id>/', views.edit_user, name='edit_user'),
    path('transfer/<int:user_id>/', views.transfer_salesperson, name='transfer_salesperson'),
    path('assign-teamlead/<int:user_id>/', views.assign_teamlead, name='assign_teamlead'),
    path('toggle-active/<int:user_id>/', views.toggle_user_active, name='toggle_user_active'),
    path('send-password-reset/<int:user_id>/', views.send_password_reset, name='send_password_reset'),
    path('reset-mfa/<int:user_id>/', views.reset_user_mfa, name='reset_user_mfa'),
    path('unlock/<int:user_id>/', views.unlock_user, name='unlock_user'),
    path('export/', views.export_users_json, name='export_users_json'),
]

