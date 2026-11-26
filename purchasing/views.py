import csv
import io
import os
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from file_sharing.models import CompanyFileShare
from users.models import User

from .forms import (
    PriceListImportForm, ProductCategoryForm, ProductForm, SupplierForm, SupplierPriceForm,
)
from .models import Product, ProductCategory, Supplier, SupplierPrice, SupplierPriceLog


# Roles that may access the purchasing module. Executives and salespeople are
# deliberately excluded: buying costs are not visible to them in-app. The
# downloadable price-list file in the company shared folder is the only
# company-wide pricing reference (per management decision).
PURCHASING_ROLES = {'admin', 'purchasing', 'purchasing_supervisor', 'operation_mgr'}


def _purchasing_only(view_func):
    """Decorator: only admin / purchasing / purchasing_supervisor / operation_mgr may pass."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if getattr(request.user, 'role', None) not in PURCHASING_ROLES:
            raise Http404("You don't have access to the Purchasing module.")
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = getattr(view_func, '__name__', 'view')
    wrapper.__doc__ = view_func.__doc__
    return wrapper


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
@_purchasing_only
def dashboard(request):
    today = timezone.now().date()
    expiring_threshold = today + timezone.timedelta(days=30)

    context = {
        'total_suppliers': Supplier.objects.count(),
        'active_suppliers': Supplier.objects.filter(is_active=True).count(),
        'total_products': Product.objects.count(),
        'active_products': Product.objects.filter(is_active=True).count(),
        'total_prices': SupplierPrice.objects.count(),
        'active_prices': SupplierPrice.objects.filter(is_active=True).count(),
        'expiring_prices': SupplierPrice.objects.filter(
            is_active=True, valid_to__gte=today, valid_to__lte=expiring_threshold,
        ).count(),
        'suppliers': Supplier.objects.filter(is_active=True).order_by('name'),
    }
    return render(request, 'purchasing/dashboard.html', context)


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------

@login_required
@_purchasing_only
def supplier_list(request):
    suppliers = Supplier.objects.all().order_by('name')
    q = request.GET.get('q', '').strip()
    if q:
        suppliers = suppliers.filter(name__icontains=q)
    return render(request, 'purchasing/supplier_list.html', {'suppliers': suppliers, 'q': q})


@login_required
@_purchasing_only
def supplier_create(request):
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Supplier created.')
            return redirect('purchasing:supplier_list')
    else:
        form = SupplierForm()
    return render(request, 'purchasing/supplier_form.html', {'form': form, 'title': 'New Supplier'})


@login_required
@_purchasing_only
def supplier_update(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, 'Supplier updated.')
            return redirect('purchasing:supplier_detail', pk=supplier.pk)
    else:
        form = SupplierForm(instance=supplier)
    return render(request, 'purchasing/supplier_form.html', {'form': form, 'title': f'Edit {supplier.name}'})


@login_required
@_purchasing_only
def supplier_detail(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    prices = supplier.prices.select_related('product').order_by('product__sku')
    return render(request, 'purchasing/supplier_detail.html', {
        'supplier': supplier, 'prices': prices,
    })


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

@login_required
@_purchasing_only
def product_list(request):
    products = Product.objects.select_related('category').order_by('sku')
    q = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    if q:
        products = products.filter(sku__icontains=q) | products.filter(description__icontains=q)
    if category:
        products = products.filter(category_id=category)
    return render(request, 'purchasing/product_list.html', {
        'products': products, 'q': q,
        'categories': ProductCategory.objects.filter(is_active=True),
        'selected_category': category,
    })


@login_required
@_purchasing_only
def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product created.')
            return redirect('purchasing:product_list')
    else:
        form = ProductForm()
    return render(request, 'purchasing/product_form.html', {'form': form, 'title': 'New Product'})


@login_required
@_purchasing_only
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, 'Product updated.')
            return redirect('purchasing:product_list')
    else:
        form = ProductForm(instance=product)
    return render(request, 'purchasing/product_form.html', {'form': form, 'title': f'Edit {product.sku}'})


@login_required
@_purchasing_only
def product_detail(request, pk):
    """Show all suppliers carrying this product with their current price."""
    product = get_object_or_404(Product, pk=pk)
    prices = product.supplier_prices.select_related('supplier').order_by('supplier__name')
    return render(request, 'purchasing/product_detail.html', {'product': product, 'prices': prices})


# ---------------------------------------------------------------------------
# Supplier Prices (the price list)
# ---------------------------------------------------------------------------

def _log_price_change(price, previous_cost, previous_lead_time, user, notes=''):
    SupplierPriceLog.objects.create(
        price=price,
        previous_unit_cost=previous_cost,
        new_unit_cost=price.unit_cost,
        previous_lead_time_days=previous_lead_time,
        new_lead_time_days=price.lead_time_days,
        changed_by=user,
        notes=notes,
    )


@login_required
@_purchasing_only
def supplier_price_create(request, supplier_pk):
    supplier = get_object_or_404(Supplier, pk=supplier_pk)
    if request.method == 'POST':
        form = SupplierPriceForm(request.POST, supplier=supplier)
        if form.is_valid():
            price = form.save()
            _log_price_change(price, None, None, request.user, form.cleaned_data.get('notes', ''))
            messages.success(request, 'Price added.')
            return redirect('purchasing:supplier_detail', pk=supplier.pk)
    else:
        form = SupplierPriceForm(supplier=supplier)
    return render(request, 'purchasing/supplier_price_form.html', {
        'form': form, 'supplier': supplier, 'title': f'Add Price — {supplier.name}',
    })


@login_required
@_purchasing_only
def supplier_price_update(request, pk):
    price = get_object_or_404(SupplierPrice, pk=pk)
    previous_cost = price.unit_cost
    previous_lead_time = price.lead_time_days
    if request.method == 'POST':
        form = SupplierPriceForm(request.POST, instance=price)
        if form.is_valid():
            price = form.save()
            if price.unit_cost != previous_cost or price.lead_time_days != previous_lead_time:
                _log_price_change(price, previous_cost, previous_lead_time, request.user,
                                  form.cleaned_data.get('notes', ''))
            messages.success(request, 'Price updated.')
            return redirect('purchasing:supplier_detail', pk=price.supplier_id)
    else:
        form = SupplierPriceForm(instance=price)
    return render(request, 'purchasing/supplier_price_form.html', {
        'form': form, 'supplier': price.supplier, 'title': f'Edit Price — {price.product.sku}',
    })


@login_required
@_purchasing_only
def supplier_price_history(request, pk):
    price = get_object_or_404(SupplierPrice, pk=pk)
    logs = price.logs.all()
    return render(request, 'purchasing/supplier_price_history.html', {
        'price': price, 'logs': logs,
    })


# ---------------------------------------------------------------------------
# Price list import (Excel/CSV -> DB + company shared folder)
# ---------------------------------------------------------------------------

def _parse_decimal(raw):
    if raw is None:
        return None
    raw = str(raw).strip().replace(',', '')
    if not raw:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def _parse_int(raw):
    if raw is None:
        return None
    try:
        return int(float(str(raw).strip()))
    except (ValueError, TypeError):
        return None


def _read_rows(uploaded_file):
    """Return a list of dicts (header -> value) from an xlsx or csv upload."""
    name = uploaded_file.name.lower()
    if name.endswith('.csv'):
        text = uploaded_file.read().decode('utf-8-sig', errors='replace')
        reader = csv.DictReader(io.StringIO(text))
        return list(reader)
    # Assume xlsx
    from openpyxl import load_workbook
    wb = load_workbook(filename=io.BytesIO(uploaded_file.read()), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(c).strip() if c is not None else '' for c in rows[0]]
    result = []
    for row in rows[1:]:
        if all(c is None or str(c).strip() == '' for c in row):
            continue
        result.append({headers[i]: row[i] if i < len(row) else None for i in range(len(headers))})
    return result


@login_required
@_purchasing_only
def pricelist_import(request):
    if request.method == 'POST':
        form = PriceListImportForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = request.FILES['file']
            currency = form.cleaned_data.get('currency') or 'PHP'
            notes = form.cleaned_data.get('notes', '')
            try:
                rows = _read_rows(uploaded)
            except Exception as exc:
                messages.error(request, f'Could not read file: {exc}')
                return redirect('purchasing:pricelist_import')

            suppliers_created = 0
            products_created = 0
            prices_created = 0
            prices_updated = 0
            skipped = 0

            try:
                with transaction.atomic():
                    for row in rows:
                        supplier_name = str(row.get('Supplier Name') or row.get('Supplier') or '').strip()
                        sku = str(row.get('Product SKU') or row.get('SKU') or row.get('Part Number') or '').strip()
                        description = str(row.get('Description') or '').strip()
                        raw_cost = row.get('Unit Cost') or row.get('Cost') or row.get('Price')
                        unit_cost = _parse_decimal(raw_cost)
                        lead_time = _parse_int(row.get('Lead Time') or row.get('Lead Time (days)'))

                        if not supplier_name or not sku or unit_cost is None:
                            skipped += 1
                            continue

                        supplier, created = Supplier.objects.get_or_create(
                            name=supplier_name,
                            defaults={'contact_person': str(row.get('Contact Person') or '').strip(),
                                      'email': str(row.get('Supplier Email') or '').strip(),
                                      'phone': str(row.get('Supplier Phone') or '').strip()},
                        )
                        if created:
                            suppliers_created += 1

                        product, created = Product.objects.get_or_create(
                            sku=sku,
                            defaults={'description': description or sku},
                        )
                        if created:
                            products_created += 1

                        price, created = SupplierPrice.objects.get_or_create(
                            supplier=supplier, product=product,
                            defaults={
                                'unit_cost': unit_cost,
                                'currency': currency,
                                'lead_time_days': lead_time,
                                'notes': notes,
                            },
                        )
                        if created:
                            prices_created += 1
                            _log_price_change(price, None, None, request.user, notes)
                        else:
                            prev_cost = price.unit_cost
                            prev_lead = price.lead_time_days
                            changed = (price.unit_cost != unit_cost or price.lead_time_days != lead_time
                                       or price.currency != currency)
                            if changed:
                                price.unit_cost = unit_cost
                                price.lead_time_days = lead_time
                                price.currency = currency
                                if notes:
                                    price.notes = notes
                                price.save()
                                prices_updated += 1
                                _log_price_change(price, prev_cost, prev_lead, request.user, notes)
            except Exception as exc:
                messages.error(request, f'Import failed: {exc}')
                return redirect('purchasing:pricelist_import')

            # Publish the file to the company shared folder so every user can
            # download the price list.
            try:
                uploaded.seek(0)
                CompanyFileShare.objects.create(
                    title=f'Supplier Price List — {timezone.now().strftime("%Y-%m-%d %H:%M")}',
                    description=notes or 'Imported supplier price list',
                    file=uploaded,
                    category='resources',
                    uploaded_by=request.user,
                )
            except Exception as exc:
                messages.warning(request, f'Imported data saved, but could not publish to shared folder: {exc}')

            messages.success(
                request,
                f'Import complete. Suppliers: +{suppliers_created}, Products: +{products_created}, '
                f'Prices: +{prices_created}, Updated: {prices_updated}, Skipped: {skipped}. '
                f'Price list published to company shared folder.'
            )
            return redirect('purchasing:dashboard')
    else:
        form = PriceListImportForm()
    return render(request, 'purchasing/pricelist_import.html', {'form': form})
