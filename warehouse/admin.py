from django.contrib import admin

from .models import BacklogReason, Delivery, DeliveryEvent, WarehouseStaff


@admin.register(WarehouseStaff)
class WarehouseStaffAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']
    list_editable = ['is_active']
    list_filter = ['is_active']
    search_fields = ['name']
    ordering = ['name']


@admin.register(BacklogReason)
class BacklogReasonAdmin(admin.ModelAdmin):
    list_display = ['name', 'reason_group', 'sort_order', 'is_active']
    list_editable = ['sort_order', 'is_active']
    list_filter = ['reason_group', 'is_active']
    search_fields = ['name']
    ordering = ['reason_group', 'sort_order', 'name']


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = [
        'so_number', 'client', 'item', 'area', 'ae',
        'driver_staff', 'vehicle_plate', 'warehouse_staff', 'backlog_reason', 'status',
        'scheduled_date', 'accomplished_date', 'updated_at',
    ]
    list_filter = [
        'status', 'ae', 'warehouse_staff', 'backlog_reason',
        'scheduled_date', 'accomplished_date',
    ]
    search_fields = [
        'so_number', 'client', 'item', 'area', 'ae',
        'driver_staff', 'vehicle_plate', 'remarks',
        'backlog_reason__name',
        'warehouse_staff__name',
    ]
    # Inline editing so warehouse staff can flip statuses and assign a
    # driver / plate / staff straight from the change list.
    list_editable = ['status', 'driver_staff', 'vehicle_plate', 'warehouse_staff', 'backlog_reason']
    list_select_related = ['warehouse_staff', 'backlog_reason']
    readonly_fields = ['updated_at']
    date_hierarchy = 'scheduled_date'
    ordering = ['-updated_at']


@admin.register(DeliveryEvent)
class DeliveryEventAdmin(admin.ModelAdmin):
    list_display = [
        'created_at', 'so_number', 'action', 'from_status', 'to_status',
        'backlog_reason', 'changed_by',
    ]
    list_filter = ['action', 'from_status', 'to_status', 'backlog_reason', 'changed_by']
    search_fields = [
        'so_number', 'remarks', 'previous_remarks', 'note',
        'backlog_reason', 'previous_backlog_reason',
    ]
    list_select_related = ['delivery', 'changed_by']
    readonly_fields = [
        'delivery', 'so_number', 'action', 'from_status', 'to_status',
        'previous_remarks', 'remarks', 'previous_backlog_reason', 'backlog_reason',
        'note', 'changed_by', 'created_at',
    ]
    ordering = ['-created_at', '-pk']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
