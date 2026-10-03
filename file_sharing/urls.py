from django.urls import path
from . import views

urlpatterns = [
    # Group file management
    path('group/<int:group_id>/files/', views.group_files, name='group_files'),
    path('group/<int:group_id>/upload/', views.upload_file, name='upload_file'),
    
    # File operations
    path('file/<int:file_id>/', views.file_details, name='file_details'),
    path('file/<int:file_id>/download/', views.download_file, name='download_file'),
    path('file/<int:file_id>/view/', views.view_file, name='view_file'),
    path('file/<int:file_id>/edit/', views.edit_file, name='edit_file'),
    path('file/<int:file_id>/delete/', views.delete_file, name='delete_file'),
    
    # Quick upload options
    path('quick-upload/', views.quick_upload, name='quick_upload'),
    path('upload-selector/', views.upload_selector, name='upload_selector'),
    
    # User file management
    path('my-files/', views.my_files, name='my_files'),
    path('all-files/', views.all_groups_files, name='all_files'),

    # Company-wide shared files (readable by everyone)
    path('company/', views.company_files, name='company_files'),
    path('company/upload/', views.company_upload, name='company_upload'),
    path('company/<int:file_id>/edit/', views.company_edit, name='company_edit'),
    path('company/<int:file_id>/download/', views.company_download, name='company_download'),
    path('company/<int:file_id>/view/', views.company_view, name='company_view'),
    path('company/<int:file_id>/delete/', views.company_delete, name='company_delete'),
]
