from django.urls import path
from . import views
from . import multi_option_views

urlpatterns = [
    path('', views.proposal_list, name='proposal_list'),
    path('export/excel/', views.export_proposals_excel, name='export_proposals_excel'),
    path('approvals/tiers/', views.approval_tier_list, name='approval_tier_list'),
    path('approvals/tiers/create/', views.approval_tier_create, name='approval_tier_create'),
    path('approvals/tiers/<int:pk>/edit/', views.approval_tier_edit, name='approval_tier_edit'),
    path('approvals/tiers/<int:pk>/delete/', views.approval_tier_delete, name='approval_tier_delete'),
    path('approvals/tiers/export/', views.approval_tier_export, name='approval_tier_export'),
    path('approvals/tiers/import/', views.approval_tier_import, name='approval_tier_import'),
    path('approvals/tiers/template/', views.approval_tier_template, name='approval_tier_template'),
    path('approvals/tiers/seed-defaults/', views.approval_tier_seed_defaults, name='approval_tier_seed_defaults'),
    path('create/', views.proposal_create, name='proposal_create'),
    path('create/multi-option/', multi_option_views.multi_option_proposal_create, name='multi_option_proposal_create'),
    path('<int:pk>/', views.proposal_detail, name='proposal_detail'),
    path('<int:pk>/edit/', views.proposal_update, name='proposal_update'),
    path('<int:pk>/edit/multi-option/', multi_option_views.multi_option_proposal_update, name='multi_option_proposal_update'),
    path('<int:pk>/delete/', views.proposal_delete, name='proposal_delete'),
    path('<int:pk>/pdf/', views.proposal_pdf, name='proposal_pdf'),
    path('<int:pk>/email/', views.proposal_email, name='proposal_email'),
    path('approvals/inbox/', views.approvals_inbox, name='approvals_inbox'),
    path('<int:pk>/approve/', views.approve_proposal, name='approve_proposal'),
    path('<int:pk>/reject/', views.reject_proposal, name='reject_proposal'),
]
