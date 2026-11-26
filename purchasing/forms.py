from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, HTML, Layout, Row, Column, Submit, Field

from .models import Product, ProductCategory, Supplier, SupplierPrice


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'contact_person', 'email', 'phone', 'address', 'payment_terms', 'is_active']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field('name'),
            Row(
                Column('contact_person', css_class='form-group col-md-6 mb-3'),
                Column('email', css_class='form-group col-md-6 mb-3'),
            ),
            Row(
                Column('phone', css_class='form-group col-md-6 mb-3'),
                Column('payment_terms', css_class='form-group col-md-6 mb-3'),
            ),
            Field('address'),
            Field('is_active'),
            Div(
                Submit('submit', 'Save Supplier', css_class='btn btn-primary btn-sm me-2'),
                HTML('<a href="{% if form.instance.pk %}{% url "purchasing:supplier_detail" form.instance.pk %}{% else %}{% url "purchasing:supplier_list" %}{% endif %}" class="btn btn-outline-secondary btn-sm">Cancel</a>'),
                css_class='d-flex align-items-center',
            ),
        )


class ProductCategoryForm(forms.ModelForm):
    class Meta:
        model = ProductCategory
        fields = ['name', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field('name'),
            Field('is_active'),
            Div(
                Submit('submit', 'Save', css_class='btn btn-primary btn-sm me-2'),
                HTML('<a href="{% url "purchasing:product_list" %}" class="btn btn-outline-secondary btn-sm">Cancel</a>'),
                css_class='d-flex align-items-center',
            ),
        )


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['sku', 'description', 'category', 'default_uom', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('sku', css_class='form-group col-md-4 mb-3'),
                Column('category', css_class='form-group col-md-4 mb-3'),
                Column('default_uom', css_class='form-group col-md-4 mb-3'),
            ),
            Field('description'),
            Field('is_active'),
            Div(
                Submit('submit', 'Save Product', css_class='btn btn-primary btn-sm me-2'),
                HTML('<a href="{% url "purchasing:product_list" %}" class="btn btn-outline-secondary btn-sm">Cancel</a>'),
                css_class='d-flex align-items-center',
            ),
        )


class SupplierPriceForm(forms.ModelForm):
    class Meta:
        model = SupplierPrice
        fields = [
            'supplier', 'product', 'unit_cost', 'currency', 'lead_time_days',
            'valid_from', 'valid_to', 'is_active', 'notes',
        ]
        widgets = {
            'valid_from': forms.DateInput(attrs={'type': 'date'}),
            'valid_to': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        supplier = kwargs.pop('supplier', None)
        super().__init__(*args, **kwargs)
        if supplier:
            self.fields['supplier'].initial = supplier
            self.fields['supplier'].widget = forms.HiddenInput()
        self.fields['supplier'].queryset = Supplier.objects.filter(is_active=True)
        self.fields['product'].queryset = Product.objects.filter(is_active=True)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field('supplier'),
            Row(
                Column('product', css_class='form-group col-md-6 mb-3'),
                Column('unit_cost', css_class='form-group col-md-3 mb-3'),
                Column('currency', css_class='form-group col-md-3 mb-3'),
            ),
            Row(
                Column('lead_time_days', css_class='form-group col-md-4 mb-3'),
                Column('valid_from', css_class='form-group col-md-4 mb-3'),
                Column('valid_to', css_class='form-group col-md-4 mb-3'),
            ),
            Field('notes'),
            Field('is_active'),
            Div(
                Submit('submit', 'Save Price', css_class='btn btn-primary btn-sm me-2'),
                HTML('<a href="{% if form.instance.pk %}{% url "purchasing:supplier_detail" form.instance.supplier_id %}{% else %}{% url "purchasing:supplier_detail" supplier.pk %}{% endif %}" class="btn btn-outline-secondary btn-sm">Cancel</a>'),
                css_class='d-flex align-items-center',
            ),
        )


class PriceListImportForm(forms.Form):
    """Upload a supplier price list (Excel/CSV).

    The file is parsed to populate Supplier/Product/SupplierPrice and is also
    saved to the company-wide shared folder so every user can download it.
    """

    file = forms.FileField(
        help_text='Upload an .xlsx or .csv price list. Required columns: Supplier Name, Product SKU, Description, Unit Cost.',
    )
    currency = forms.CharField(max_length=10, initial='PHP', required=False)
    notes = forms.CharField(
        required=False, widget=forms.Textarea(attrs={'rows': 2}),
        help_text='Optional note stored with every price row (e.g. price list version).',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field('file'),
            Row(
                Column('currency', css_class='form-group col-md-4 mb-3'),
            ),
            Field('notes'),
            Div(
                Submit('submit', 'Upload & Import', css_class='btn btn-primary btn-sm me-2'),
                HTML('<a href="{% url "purchasing:dashboard" %}" class="btn btn-outline-secondary btn-sm">Cancel</a>'),
                css_class='d-flex align-items-center',
            ),
        )
