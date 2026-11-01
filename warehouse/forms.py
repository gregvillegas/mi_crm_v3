from django import forms
from django.db.models import Q

from .models import Delivery, WarehouseStaff


class DeliveryForm(forms.ModelForm):
    """Add / edit form used by the warehouse role on the delivery board."""

    class Meta:
        model = Delivery
        fields = [
            'so_number', 'client', 'item', 'area',
            'driver_staff', 'vehicle_plate', 'warehouse_staff',
            'ae', 'remarks', 'status', 'scheduled_date', 'accomplished_date',
        ]
        widgets = {
            'scheduled_date': forms.DateInput(attrs={'type': 'date'}),
            'accomplished_date': forms.DateInput(attrs={'type': 'date'}),
            'remarks': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The staff dropdown only offers active names, but a delivery already
        # pointing at a since-deactivated name keeps working.
        staff = WarehouseStaff.objects.filter(is_active=True)
        if self.instance.pk and self.instance.warehouse_staff_id:
            staff = WarehouseStaff.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.warehouse_staff_id)
            )
        self.fields['warehouse_staff'].queryset = staff.order_by('name')
        self.fields['warehouse_staff'].required = False
        self.fields['warehouse_staff'].empty_label = '---------'
