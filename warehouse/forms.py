from django import forms
from django.db.models import Q

from .models import (
    BacklogReason,
    Delivery,
    WarehouseStaff,
    get_transition_backlog_reason_error,
    get_transition_remarks_error,
)


class DeliveryForm(forms.ModelForm):
    """Add / edit form used by the warehouse role on the delivery board."""

    class Meta:
        model = Delivery
        fields = [
            'so_number', 'client', 'item', 'area',
            'driver_staff', 'vehicle_plate', 'warehouse_staff',
            'backlog_reason',
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
        reasons = BacklogReason.objects.filter(is_active=True)
        if self.instance.pk and self.instance.backlog_reason_id:
            reasons = BacklogReason.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.backlog_reason_id)
            )
        self.fields['backlog_reason'].queryset = reasons.order_by(
            'reason_group', 'sort_order', 'name'
        )
        self.fields['backlog_reason'].required = False
        self.fields['backlog_reason'].empty_label = '---------'
        self.fields['backlog_reason'].help_text = (
            'Required when moving a delivery back to For Schedule so backlog '
            'reporting stays structured.'
        )
        self.fields['remarks'].help_text = (
            'Use remarks as the current stage note. When changing status, enter '
            'the scheduling note, completion outcome, or backlog reason here.'
        )

    def clean(self):
        cleaned_data = super().clean()
        if not self.instance.pk:
            return cleaned_data

        old_status = self.instance.status
        new_status = cleaned_data.get('status')
        remarks = (cleaned_data.get('remarks') or '').strip()
        backlog_reason = cleaned_data.get('backlog_reason')
        error = get_transition_remarks_error(old_status, new_status, remarks)
        reason_error = get_transition_backlog_reason_error(
            old_status, new_status, backlog_reason
        )

        if error:
            self.add_error('remarks', error)
        if reason_error:
            self.add_error('backlog_reason', reason_error)

        return cleaned_data


class BacklogReasonForm(forms.ModelForm):
    """Warehouse-managed backlog reason catalog entry."""

    class Meta:
        model = BacklogReason
        fields = ['name', 'reason_group', 'sort_order', 'is_active']


class ScheduledDeliveryImportForm(forms.Form):
    """Upload form for staged migration from Excel/CSV into the dashboard."""

    file = forms.FileField()

    def clean_file(self):
        uploaded_file = self.cleaned_data['file']
        file_name = (uploaded_file.name or '').lower()
        if not file_name.endswith(('.xlsx', '.xlsm', '.csv')):
            raise forms.ValidationError(
                'Please upload an .xlsx, .xlsm, or .csv file.'
            )
        return uploaded_file
