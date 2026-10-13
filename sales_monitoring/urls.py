from django.urls import path
from . import views

app_name = 'sales_monitoring'

urlpatterns = [
    # Main dashboard routes
    path('', views.dashboard, name='dashboard'),
    path('supervisor/', views.supervisor_dashboard, name='supervisor_dashboard'),
    path('salesperson/', views.salesperson_dashboard, name='salesperson_dashboard'),
    path('salesperson/activities/', views.salesperson_activity_list, name='salesperson_activities'),
    path('admin/', views.admin_dashboard, name='admin_dashboard'),
    path('executive/', views.executive_dashboard, name='executive_dashboard'),
    path('avp/group/<int:group_id>/activities/', views.avp_group_activities, name='avp_group_activities'),
    path('group/<int:group_id>/fiscal-summary/', views.group_fiscal_summary, name='group_fiscal_summary'),
    path('group/<int:group_id>/fiscal-summary/export/excel/', views.export_group_fiscal_summary_excel, name='export_group_fiscal_summary_excel'),
    path('group/<int:group_id>/fiscal-summary/export/pdf/', views.export_group_fiscal_summary_pdf, name='export_group_fiscal_summary_pdf'),
    path('team-performance/export/excel/', views.export_team_fiscal_summary_excel, name='export_team_fiscal_summary_excel'),
    path('fiscal-year-comparison/', views.fiscal_year_comparison, name='fiscal_year_comparison'),
    path('fiscal-year-comparison/export/excel/', views.export_fiscal_year_comparison_excel, name='export_fiscal_year_comparison_excel'),
    path('fiscal-year-comparison/export/pdf/', views.export_fiscal_year_comparison_pdf, name='export_fiscal_year_comparison_pdf'),
    
    # Activity management
    path('activity/create/', views.create_activity, name='create_activity'),
    path('poc/create/', views.create_poc, name='create_poc'),
    path('activity/<int:pk>/', views.activity_detail, name='activity_detail'),
    path('activity/<int:pk>/update/', views.update_activity, name='update_activity'),
    path('quick-log/', views.quick_log_activity, name='quick_log_activity'),
    
    # Monitoring and reporting
    path('team-performance/', views.team_performance, name='team_performance'),
    path('group-performance/', views.group_performance, name='group_performance'),
    path('reports/', views.activity_reports, name='activity_reports'),
    path('calendar/', views.activity_calendar, name='activity_calendar'),
    path('bulk-update/', views.bulk_update_activities, name='bulk_update_activities'),
    
    # Data export
    path('export/', views.export_activities, name='export_activities'),
]
