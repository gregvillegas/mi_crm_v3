from django.contrib import admin

from .models import Product, ProductCategory, Supplier, SupplierPrice, SupplierPriceLog


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('sku', 'description', 'category', 'default_uom', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('sku', 'description')


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_person', 'email', 'phone', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'contact_person', 'email')


@admin.register(SupplierPrice)
class SupplierPriceAdmin(admin.ModelAdmin):
    list_display = ('supplier', 'product', 'unit_cost', 'currency', 'lead_time_days', 'is_active')
    list_filter = ('currency', 'is_active')
    search_fields = ('supplier__name', 'product__sku', 'product__description')


@admin.register(SupplierPriceLog)
class SupplierPriceLogAdmin(admin.ModelAdmin):
    """Read-only audit log."""
    list_display = ('price', 'previous_unit_cost', 'new_unit_cost', 'changed_by', 'changed_at')
    list_filter = ('changed_at',)
    readonly_fields = (
        'price', 'previous_unit_cost', 'new_unit_cost',
        'previous_lead_time_days', 'new_lead_time_days',
        'changed_by', 'changed_at', 'notes',
    )
    search_fields = ('price__product__sku', 'changed_by__username')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
