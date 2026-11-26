from django.urls import path

from . import views

app_name = 'purchasing'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    # Suppliers
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/new/', views.supplier_create, name='supplier_create'),
    path('suppliers/<int:pk>/', views.supplier_detail, name='supplier_detail'),
    path('suppliers/<int:pk>/edit/', views.supplier_update, name='supplier_update'),
    # Products
    path('products/', views.product_list, name='product_list'),
    path('products/new/', views.product_create, name='product_create'),
    path('products/<int:pk>/', views.product_detail, name='product_detail'),
    path('products/<int:pk>/edit/', views.product_update, name='product_update'),
    # Supplier prices
    path('suppliers/<int:supplier_pk>/prices/new/', views.supplier_price_create, name='supplier_price_create'),
    path('prices/<int:pk>/edit/', views.supplier_price_update, name='supplier_price_update'),
    path('prices/<int:pk>/history/', views.supplier_price_history, name='supplier_price_history'),
    # Import
    path('import/', views.pricelist_import, name='pricelist_import'),
]
