from django.contrib import admin

from .models import Delivery, WarehouseStaff


@admin.register(WarehouseStaff)
class WarehouseStaffAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']
    list_editable = ['is_active']
    list_filter = ['is_active']
    search_fields = ['name']
    ordering = ['name']


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = [
        'so_number', 'client', 'item', 'area', 'ae',
        'driver_staff', 'vehicle_plate', 'warehouse_staff', 'status',
        'scheduled_date', 'accomplished_date', 'updated_at',
    ]
    list_filter = ['status', 'ae', 'warehouse_staff', 'scheduled_date', 'accomplished_date']
    search_fields = [
        'so_number', 'client', 'item', 'area', 'ae',
        'driver_staff', 'vehicle_plate', 'remarks',
        'warehouse_staff__name',
    ]
    # Inline editing so warehouse staff can flip statuses and assign a
    # driver / plate / staff straight from the change list.
    list_editable = ['status', 'driver_staff', 'vehicle_plate', 'warehouse_staff']
    list_select_related = ['warehouse_staff']
    readonly_fields = ['updated_at']
    date_hierarchy = 'scheduled_date'
    ordering = ['-updated_at']
