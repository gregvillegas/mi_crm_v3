from django.conf import settings
from django.db import models
from django.utils import timezone


class ProductCategory(models.Model):
    """Lookup category for the product catalog (e.g. Medical, IT, Furniture)."""

    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Product Category'
        verbose_name_plural = 'Product Categories'

    def __str__(self):
        return self.name


class Product(models.Model):
    """
    Canonical product catalog master.

    Products exist independently of any proposal or supplier so that supplier
    prices, purchase orders, and (later) inventory can all reference the same
    SKU. Free-text proposal items remain untouched in Phase 1.
    """

    sku = models.CharField(max_length=100, unique=True, help_text='Internal part number / SKU')
    description = models.TextField()
    category = models.ForeignKey(
        ProductCategory, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='products',
    )
    default_uom = models.CharField(max_length=30, default='unit', help_text='e.g. unit, box, meter')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sku']

    def __str__(self):
        return f'{self.sku} - {self.description[:60]}'


class Supplier(models.Model):
    """Vendor / supplier master record."""

    name = models.CharField(max_length=200, unique=True)
    contact_person = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    payment_terms = models.CharField(
        max_length=100, blank=True, help_text='e.g. Net 30, 50% down',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class SupplierPrice(models.Model):
    """
    A single buying-price entry: one supplier + one product.

    Kept one-row-per-(supplier, product) with `unique_together`; the full
    change history lives in SupplierPriceLog. This mirrors the quota-log
    pattern used for TeamMembership.quota.
    """

    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='prices')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='supplier_prices')
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default='PHP')
    lead_time_days = models.PositiveIntegerField(
        null=True, blank=True, help_text='Typical delivery lead time from this supplier',
    )
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('supplier', 'product')
        ordering = ['supplier__name', 'product__sku']

    def __str__(self):
        return f'{self.supplier.name} / {self.product.sku} @ {self.currency} {self.unit_cost}'

    @property
    def is_expiring(self, days=30):
        if not self.valid_to:
            return False
        return timezone.now().date() <= self.valid_to <= timezone.now().date() + timezone.timedelta(days=days)


class SupplierPriceLog(models.Model):
    """Immutable audit row for every SupplierPrice create / edit."""

    price = models.ForeignKey(SupplierPrice, on_delete=models.CASCADE, related_name='logs')
    previous_unit_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    new_unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    previous_lead_time_days = models.PositiveIntegerField(null=True)
    new_lead_time_days = models.PositiveIntegerField(null=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='supplier_price_logs',
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-changed_at']
        verbose_name = 'Supplier Price Log'
        verbose_name_plural = 'Supplier Price Logs'

    def __str__(self):
        who = self.changed_by.get_full_name() if self.changed_by else 'system'
        return f'{self.price.product.sku}: {self.previous_unit_cost} -> {self.new_unit_cost} by {who}'
