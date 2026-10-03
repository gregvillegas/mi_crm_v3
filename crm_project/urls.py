# -----------------------------------------------------------------------------
# 7. crm_project/urls.py
# -----------------------------------------------------------------------------
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from core.views import home, logout_view, global_search
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from rest_framework import routers
from users.api import UserViewSet
from crm_project.api_auth import CustomAuthToken, LogoutView, MfaAuthToken
from crm_project.api_views import (
    ActivityTypeViewSet,
    CampaignViewSet,
    CustomerCreateRequestViewSet,
    CustomerViewSet,
    DashboardView,
    GlobalSearchView,
    ProposalViewSet,
    SalesActivityViewSet,
    SalesFunnelViewSet,
)

# API Router
router = routers.DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'customers', CustomerViewSet, basename='customers')
router.register(r'customer-requests', CustomerCreateRequestViewSet, basename='customer-requests')
router.register(r'funnel', SalesFunnelViewSet, basename='funnel')
router.register(r'proposals', ProposalViewSet, basename='proposals')
router.register(r'activities', SalesActivityViewSet, basename='activities')
router.register(r'activity-types', ActivityTypeViewSet, basename='activity-types')
router.register(r'campaigns', CampaignViewSet, basename='campaigns')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include(router.urls)),
    path('api/v1/api-token-auth/', CustomAuthToken.as_view(), name='api-token-auth'),
    path('api/v1/api-token-auth/mfa/', MfaAuthToken.as_view(), name='api-token-auth-mfa'),
    path('api/v1/logout/', LogoutView.as_view(), name='api-logout'),
    path('api/v1/dashboard/', DashboardView.as_view(), name='api-dashboard'),
    path('api/v1/search/', GlobalSearchView.as_view(), name='api-search'),
    path('', home, name='home'),
    path('search/', global_search, name='global_search'),
    path('customers/', include('customers.urls')),
    path('users/', include('users.urls')), # <-- ADDED
    path('teams/', include('teams.urls')), # <-- ADDED
    path('funnel/', include('sales_funnel.urls')), # <-- ADDED
    path('sales-monitoring/', include('sales_monitoring.urls')), # <-- ADDED
    path('leads/', include('lead_generation.urls')), # <-- ADDED
    path('files/', include('file_sharing.urls')), # <-- ADDED
    path('proposals/', include('sales_proposals.urls')), # <-- ADDED
    path('gamification/', include('gamification.urls')), # <-- ADDED
    path('service/', include('customer_service.urls')),
    # Login handled by allauth (supports MFA/TOTP challenge after password)
    path('login/', RedirectView.as_view(url='/accounts/login/', query_string=True), name='login'),
    path('logout/', logout_view, name='logout'),
    path('accounts/', include('allauth.urls')),  # allauth + mfa URLs
    path('accounts/2fa/', include('allauth.mfa.urls')),  # MFA URLs (TOTP setup, authenticator)
    path('mass-mailing/', include('mass_mailing.urls')),
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
