from django.contrib import admin

from .models import Delivery


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = [
        'so_number', 'client', 'item', 'area', 'ae',
        'driver_staff', 'vehicle_plate', 'status',
        'scheduled_date', 'accomplished_date', 'updated_at',
    ]
    list_filter = ['status', 'ae', 'scheduled_date', 'accomplished_date']
    search_fields = [
        'so_number', 'client', 'item', 'area', 'ae',
        'driver_staff', 'vehicle_plate', 'remarks',
    ]
    # Inline editing so warehouse staff can flip statuses and assign a
    # driver / plate straight from the change list.
    list_editable = ['status', 'driver_staff', 'vehicle_plate']
    readonly_fields = ['updated_at']
    date_hierarchy = 'scheduled_date'
    ordering = ['-updated_at']
