"""
Forms for Multi-Option Proposals.
Handles option groups and their items separately from the standard single-format proposal.
"""
from decimal import Decimal, InvalidOperation
from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from .models import Proposal, ProposalOptionGroup, ProposalItem, ProposalAttachment
from .forms import ProposalForm, ProposalAttachmentForm


class MultiOptionProposalForm(ProposalForm):
    """
    Same as ProposalForm but forces is_multi_option=True on save.
    Hides the show_discount and is_optional concepts (not applicable in multi-option).
    """

    class Meta(ProposalForm.Meta):
        fields = [
            'customer',
            'contact_name',
            'contact_email',
            'contact_phone',
            'subject',
            'currency',
            'exchange_rate',
            'date',
            'valid_until',
            'stock_availability',
            'payment_terms',
            'delivery_lead_time',
            'show_vat',
            'use_availability_column',
            'hide_part_number',
            'include_bank_details',
            # Bank details
            'php_bank_name', 'php_account_name', 'php_account_number', 'php_account_type',
            'php_branch', 'php_bank_address', 'php_swift_code', 'php_branch_code',
            'php_bpi_account_name', 'php_bpi_account_number', 'php_bpi_account_type',
            'php_bpi_branch', 'php_bpi_bank_address', 'php_bpi_swift_code',
            'usd_beneficiary_name', 'usd_beneficiary_address', 'usd_account_number',
            'usd_bank_name', 'usd_bank_address', 'usd_swift_code', 'usd_branch_code',
            'introduction',
            'special_note',
            'closing',
        ]

    def __init__(self, *args, **kwargs):
        # Skip ProposalForm's __init__ discount_amount handling by calling grandparent
        user = kwargs.pop('user', None)
        forms.ModelForm.__init__(self, *args, **kwargs)
        self.user = user
        # Apply customer queryset filtering (same logic as parent)
        from customers.models import Customer
        from teams.models import Team, Group, TeamMembership
        from django.db.models import Q
        qs = Customer.objects.filter(is_active=True)
        role = getattr(self.user, 'role', None) if self.user else None
        if role == 'salesperson':
            qs = qs.filter(salesperson=self.user)
        elif role == 'supervisor':
            groups = Group.objects.filter(supervisor=self.user)
            sp_ids = TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)
            qs = qs.filter(Q(salesperson_id__in=sp_ids) | Q(salesperson=self.user))
        elif role == 'teamlead':
            groups = Group.objects.filter(teamlead=self.user)
            sp_ids = TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)
            qs = qs.filter(Q(salesperson_id__in=sp_ids) | Q(salesperson=self.user))
        elif role in ['asm', 'sm']:
            asm_teams = getattr(self.user, 'asm_teams', None)
            team_qs = asm_teams.all() if asm_teams is not None else Team.objects.none()
            groups = Group.objects.filter(team__in=team_qs)
            sp_ids = TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)
            qs = qs.filter(Q(salesperson_id__in=sp_ids) | Q(salesperson=self.user))
        elif role == 'avp':
            teams = Team.objects.filter(avp=self.user)
            groups = Group.objects.filter(team__in=teams)
            sp_ids = TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)
            qs = qs.filter(Q(salesperson_id__in=sp_ids) | Q(salesperson=self.user))
        self.fields['customer'].queryset = qs

        # Bank detail fields are optional — only used if include_bank_details is checked
        bank_fields = [
            'php_bank_name', 'php_account_name', 'php_account_number', 'php_account_type',
            'php_branch', 'php_bank_address', 'php_swift_code', 'php_branch_code',
            'php_bpi_account_name', 'php_bpi_account_number', 'php_bpi_account_type',
            'php_bpi_branch', 'php_bpi_bank_address', 'php_bpi_swift_code',
            'usd_beneficiary_name', 'usd_beneficiary_address', 'usd_account_number',
            'usd_bank_name', 'usd_bank_address', 'usd_swift_code', 'usd_branch_code',
        ]
        for field_name in bank_fields:
            if field_name in self.fields:
                self.fields[field_name].required = False

    def save(self, commit=True):
        instance = super(forms.ModelForm, self).save(commit=False)
        instance.is_multi_option = True
        if commit:
            instance.save()
        return instance


class ProposalOptionGroupForm(forms.ModelForm):
    """Form for a single option group (name + sort order)."""

    class Meta:
        model = ProposalOptionGroup
        fields = ['name', 'sort_order', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., OPTION 1'}),
            'sort_order': forms.HiddenInput(),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional notes for this option'}),
        }


# Formset for option groups within a proposal
OptionGroupFormSet = inlineformset_factory(
    Proposal,
    ProposalOptionGroup,
    form=ProposalOptionGroupForm,
    extra=0,
    can_delete=True,
    min_num=0,
    validate_min=False,
)


class MultiOptionItemForm(forms.ModelForm):
    """
    Item form for multi-option proposals.
    Same fields as standard ProposalItemForm but includes option_group assignment.
    """
    # Hidden field to track which option group this item belongs to (by sort_order index)
    option_group_index = forms.IntegerField(widget=forms.HiddenInput(), required=False)

    # Declare price fields as text so comma-formatted values ("2,000.00") are
    # accepted. A model-derived DecimalField rejects commas in to_python()
    # with "Enter a number." before clean_unit_cost/clean_unit_price can run.
    unit_cost = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'price-input no-spin', 'inputmode': 'decimal', 'autocomplete': 'off'}),
    )
    unit_price = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'price-input no-spin', 'inputmode': 'decimal', 'autocomplete': 'off'}),
    )

    class Meta:
        model = ProposalItem
        fields = ['part_number', 'description', 'quantity', 'unit_cost', 'unit_price', 'warranty', 'is_bundle', 'bundled_items']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'quantity': forms.NumberInput(attrs={'class': 'no-spin', 'step': '1', 'min': '1', 'inputmode': 'numeric'}),
            'bundled_items': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Paste 3–5 columns from Excel (Part Number, Description, Qty, [Unit Price], [Total Price]).\nPricing columns are ignored.',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unit_cost'].required = False
        self.fields['bundled_items'].required = False

    def _clean_decimal_text(self, field_name):
        raw_value = self.cleaned_data.get(field_name)
        if raw_value in [None, '']:
            return None
        if isinstance(raw_value, Decimal):
            return raw_value
        normalized = str(raw_value).strip().replace(',', '')
        if normalized == '':
            return None
        try:
            return Decimal(normalized)
        except (InvalidOperation, TypeError):
            raise forms.ValidationError('Enter a valid amount.')

    def clean_unit_cost(self):
        value = self._clean_decimal_text('unit_cost')
        return value if value is not None else Decimal('0')

    def clean_unit_price(self):
        value = self._clean_decimal_text('unit_price')
        if value is None:
            raise forms.ValidationError('This field is required.')
        return value

    def clean_warranty(self):
        value = (self.cleaned_data.get('warranty') or '').strip()
        limit = ProposalItem.AVAILABILITY_WARRANTY_MAX_LENGTH
        if len(value) > limit:
            raise forms.ValidationError(
                f'This value is too long ({len(value)} characters). '
                f'Please keep it under {limit} characters.'
            )
        return value


MultiOptionItemFormSet = inlineformset_factory(
    Proposal,
    ProposalItem,
    form=MultiOptionItemForm,
    extra=1,
    can_delete=True,
)


# Reuse the attachment formset from standard proposals
MultiOptionAttachmentFormSet = inlineformset_factory(
    Proposal,
    ProposalAttachment,
    form=ProposalAttachmentForm,
    extra=1,
    can_delete=True,
)
