from decimal import Decimal, InvalidOperation
from django import forms
from django.forms import inlineformset_factory
from .models import Proposal, ProposalItem, ProposalApprovalTier, ProposalAttachment
from customers.models import Customer
from teams.models import Team, Group, TeamMembership
from django.db.models import Q

from django.forms import NumberInput, TextInput, Textarea, ClearableFileInput


class ProposalForm(forms.ModelForm):
    class Meta:
        model = Proposal
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
            'include_bank_details',
            'show_discount',
            'show_vat',
            'use_availability_column',
            'hide_part_number',
            'discount_amount',
            # Bank details (editable)
            # BDO PHP
            'php_bank_name', 'php_account_name', 'php_account_number', 'php_account_type',
            'php_branch', 'php_bank_address', 'php_swift_code', 'php_branch_code',
            # BPI PHP
            'php_bpi_account_name', 'php_bpi_account_number', 'php_bpi_account_type',
            'php_bpi_branch', 'php_bpi_bank_address', 'php_bpi_swift_code',
            # USD BDO
            'usd_beneficiary_name', 'usd_beneficiary_address', 'usd_account_number',
            'usd_bank_name', 'usd_bank_address', 'usd_swift_code', 'usd_branch_code',
            'introduction',
            'special_note',
            'closing',
        ]
        labels = {
            'stock_availability': 'Stock availability',
            'closing': 'Other terms',
            # BDO PHP
            'php_bank_name': 'BDO Bank name',
            'php_account_name': 'BDO Account name',
            'php_account_number': 'BDO Account number',
            'php_account_type': 'BDO Account type',
            'php_branch': 'BDO Branch',
            'php_bank_address': 'BDO Bank address',
            'php_swift_code': 'BDO Swift code',
            'php_branch_code': 'BDO Branch code',
            # BPI PHP
            'php_bpi_account_name': 'BPI Account name',
            'php_bpi_account_number': 'BPI Account number',
            'php_bpi_account_type': 'BPI Account type',
            'php_bpi_branch': 'BPI Branch',
            'php_bpi_bank_address': 'BPI Bank address',
            'php_bpi_swift_code': 'BPI Swift code',
            # USD BDO
            'usd_beneficiary_name': 'USD Beneficiary name',
            'usd_beneficiary_address': 'USD Beneficiary address',
            'usd_account_number': 'USD Account number',
            'usd_bank_name': 'USD Bank name',
            'usd_bank_address': 'USD Bank address',
            'usd_swift_code': 'USD Swift code (BIC)',
            'usd_branch_code': 'USD Branch code',
            'show_discount': 'Show discount (PDF)',
            'show_vat': 'Include VAT 12%',
            'use_availability_column': 'Show Availability column (uncheck for Warranty)',
            'hide_part_number': 'Hide Part No. column (PDF)',
            'discount_amount': 'Discount amount',
        }
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'valid_until': forms.DateInput(attrs={'type': 'date'}),
            'stock_availability': forms.Select(attrs={'class': 'form-select'}),
            'payment_terms': forms.Textarea(attrs={'rows': 3}),
            'introduction': forms.Textarea(attrs={'rows': 3}),
            'special_note': forms.Textarea(attrs={'rows': 1}),
            'closing': forms.Textarea(attrs={'rows': 3}),
            'discount_amount': TextInput(attrs={'class': 'price-input no-spin', 'inputmode': 'decimal', 'autocomplete': 'off'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
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
        self.fields['discount_amount'].required = False
        # All bank detail fields are optional
        bank_fields = [
            'php_bank_name', 'php_account_name', 'php_account_number', 'php_account_type',
            'php_branch', 'php_bank_address', 'php_swift_code', 'php_branch_code',
            'php_bpi_account_name', 'php_bpi_account_number', 'php_bpi_account_type',
            'php_bpi_branch', 'php_bpi_bank_address', 'php_bpi_swift_code',
            'usd_beneficiary_name', 'usd_beneficiary_address', 'usd_account_number',
            'usd_bank_name', 'usd_bank_address', 'usd_swift_code', 'usd_branch_code',
        ]
        for f in bank_fields:
            if f in self.fields:
                self.fields[f].required = False

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

    def clean_discount_amount(self):
        value = self._clean_decimal_text('discount_amount')
        return value if value is not None else Decimal('0')

    def clean(self):
        cleaned_data = super().clean()
        show_discount = cleaned_data.get('show_discount')
        discount_amount = cleaned_data.get('discount_amount') or Decimal('0')
        if not show_discount:
            cleaned_data['discount_amount'] = Decimal('0')
            self.cleaned_data['discount_amount'] = Decimal('0')
            discount_amount = Decimal('0')
        if show_discount and discount_amount <= 0:
            self.add_error('discount_amount', 'Enter a discount amount greater than zero.')
        return cleaned_data


class ProposalItemForm(forms.ModelForm):
    # Declare the price fields as plain text so comma-formatted display values
    # (e.g. "2,000.00") are accepted. The DecimalField auto-generated from the
    # model runs to_python() during field validation and rejects commas with
    # "Enter a number." before our comma-stripping clean_* methods ever run.
    # Using CharField lets clean_unit_cost/clean_unit_price own the conversion.
    unit_cost = forms.CharField(
        required=False,
        widget=TextInput(attrs={'class': 'price-input no-spin', 'inputmode': 'decimal', 'autocomplete': 'off'}),
    )
    unit_price = forms.CharField(
        widget=TextInput(attrs={'class': 'price-input no-spin', 'inputmode': 'decimal', 'autocomplete': 'off'}),
    )

    class Meta:
        model = ProposalItem
        fields = ['part_number', 'description', 'quantity', 'unit_cost', 'unit_price', 'warranty', 'is_optional', 'is_bundle', 'bundled_items']
        widgets = {
            'description': Textarea(attrs={'rows': 3}),
            'quantity': NumberInput(attrs={'class': 'no-spin', 'step': '1', 'min': '1', 'inputmode': 'numeric'}),
            'warranty': TextInput(attrs={
                'class': 'form-control',
                'maxlength': ProposalItem.AVAILABILITY_WARRANTY_MAX_LENGTH,
            }),
            'bundled_items': Textarea(attrs={
                'rows': 5,
                'placeholder': 'Paste 3–5 columns from Excel (Part Number, Description, Qty, [Unit Price], [Total Price]).\nPricing columns are ignored — only Part Number, Description, and Qty are kept.\nB4YT6AV | HP IDS DSC RTX PRO 2000 8GB Ultra 9 285HX 16 inch G1i Base NB PC | 2\n8C9M7AV | No Country of Origin Restriction | 2',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['unit_cost'].required = False
        self.fields['bundled_items'].required = False
        # Enforce the shared Availability/Warranty limit at the form level so the
        # value can never exceed the DB column (this field feeds both columns).
        self.fields['warranty'].max_length = ProposalItem.AVAILABILITY_WARRANTY_MAX_LENGTH

    def clean_warranty(self):
        value = (self.cleaned_data.get('warranty') or '').strip()
        limit = ProposalItem.AVAILABILITY_WARRANTY_MAX_LENGTH
        if len(value) > limit:
            raise forms.ValidationError(
                f'This value is too long ({len(value)} characters). '
                f'Please keep it under {limit} characters.'
            )
        return value

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

    def clean(self):
        cleaned_data = super().clean()
        bundled_items = (cleaned_data.get('bundled_items') or '').strip()
        cleaned_data['bundled_items'] = bundled_items

        if cleaned_data.get('is_bundle') and not bundled_items:
            self.add_error('bundled_items', 'Enter at least one bundled part number or component line.')

        return cleaned_data

ProposalItemFormSet = inlineformset_factory(
    Proposal,
    ProposalItem,
    form=ProposalItemForm,
    extra=1,
    can_delete=True
)

class ProposalAttachmentForm(forms.ModelForm):
    class Meta:
        model = ProposalAttachment
        fields = ['file', 'include_in_email']
        widgets = {
            'file': ClearableFileInput(attrs={'multiple': False}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['include_in_email'].help_text = 'Disabled automatically for COSTING-MATRIX files.'
        uploaded = None
        try:
            uploaded = self.files.get('file')
        except Exception:
            uploaded = None

        is_costing_matrix = False
        if uploaded:
            is_costing_matrix = ProposalAttachment._is_costing_matrix_name(uploaded.name)
        elif getattr(self.instance, 'pk', None):
            is_costing_matrix = self.instance.is_costing_matrix

        if is_costing_matrix:
            self.fields['include_in_email'].disabled = True
            self.fields['include_in_email'].initial = False

    def clean(self):
        cleaned_data = super().clean()
        uploaded_file = cleaned_data.get('file') or getattr(self.instance, 'file', None)
        if uploaded_file:
            normalized = uploaded_file.name.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
            stem = normalized.rsplit('.', 1)[0]
            if ProposalAttachment._is_costing_matrix_name(stem):
                cleaned_data['include_in_email'] = False
                self.cleaned_data['include_in_email'] = False
        return cleaned_data

ProposalAttachmentFormSet = inlineformset_factory(
    Proposal,
    ProposalAttachment,
    form=ProposalAttachmentForm,
    fields=['file', 'include_in_email'],
    extra=1,
    can_delete=True
)

class ProposalApprovalTierForm(forms.ModelForm):
    class Meta:
        model = ProposalApprovalTier
        fields = ['name', 'min_amount_php', 'max_amount_php', 'chain', 'order', 'active']
        widgets = {
            'chain': forms.TextInput(attrs={'placeholder': 'supervisor,asm,avp_or_gm'}),
        }


class ProposalApprovalTierImportForm(forms.Form):
    file = forms.FileField()
    replace_existing = forms.BooleanField(required=False, initial=False)
