from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from file_sharing.models import CompanyFileShare
from purchasing.models import Product, ProductCategory, Supplier, SupplierPrice, SupplierPriceLog

User = get_user_model()


class PurchasingAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='purch_admin', password='x', role='admin')
        self.buyer = User.objects.create_user(username='purch_buyer', password='x', role='purchasing')
        self.salesperson = User.objects.create_user(username='purch_seller', password='x', role='salesperson')
        self.gm = User.objects.create_user(username='purch_gm', password='x', role='gm')
        self.operation_mgr = User.objects.create_user(username='purch_ops', password='x', role='operation_mgr')

    def test_admin_can_access_dashboard(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('purchasing:dashboard')).status_code, 200)

    def test_purchasing_role_can_access(self):
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.get(reverse('purchasing:dashboard')).status_code, 200)

    def test_operation_mgr_can_access(self):
        self.client.force_login(self.operation_mgr)
        self.assertEqual(self.client.get(reverse('purchasing:dashboard')).status_code, 200)

    def test_salesperson_blocked(self):
        self.client.force_login(self.salesperson)
        self.assertEqual(self.client.get(reverse('purchasing:dashboard')).status_code, 404)

    def test_executive_blocked(self):
        # Buying costs are not visible to executives in-app.
        self.client.force_login(self.gm)
        self.assertEqual(self.client.get(reverse('purchasing:dashboard')).status_code, 404)


class SupplierProductPriceCrudTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='pp_admin', password='x', role='admin')
        self.client.force_login(self.admin)
        self.supplier = Supplier.objects.create(name='Test Supplier', is_active=True)
        self.category = ProductCategory.objects.create(name='Medical')
        self.product = Product.objects.create(sku='SKU-001', description='Test product', category=self.category)

    def test_create_supplier(self):
        resp = self.client.post(reverse('purchasing:supplier_create'), {
            'name': 'New Supplier', 'contact_person': 'John', 'email': 'j@x.test',
            'phone': '123', 'address': '', 'payment_terms': 'Net 30', 'is_active': True,
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Supplier.objects.filter(name='New Supplier').exists())

    def test_create_product(self):
        resp = self.client.post(reverse('purchasing:product_create'), {
            'sku': 'SKU-002', 'description': 'Another', 'category': self.category.pk,
            'default_uom': 'unit', 'is_active': True,
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Product.objects.filter(sku='SKU-002').exists())

    def test_supplier_detail_lists_prices(self):
        SupplierPrice.objects.create(supplier=self.supplier, product=self.product, unit_cost=Decimal('100.00'))
        resp = self.client.get(reverse('purchasing:supplier_detail', args=[self.supplier.pk]))
        self.assertContains(resp, 'SKU-001')
        self.assertContains(resp, '100.00')

    def test_create_price_logs_audit(self):
        resp = self.client.post(reverse('purchasing:supplier_price_create', args=[self.supplier.pk]), {
            'supplier': self.supplier.pk, 'product': self.product.pk,
            'unit_cost': '250.50', 'currency': 'PHP', 'lead_time_days': '7',
            'valid_from': '', 'valid_to': '', 'is_active': True, 'notes': 'initial',
        })
        self.assertEqual(resp.status_code, 302)
        price = SupplierPrice.objects.get(supplier=self.supplier, product=self.product)
        self.assertEqual(price.unit_cost, Decimal('250.50'))
        self.assertEqual(SupplierPriceLog.objects.filter(price=price).count(), 1)
        self.assertIsNone(SupplierPriceLog.objects.get(price=price).previous_unit_cost)

    def test_update_price_logs_change(self):
        price = SupplierPrice.objects.create(supplier=self.supplier, product=self.product, unit_cost=Decimal('100.00'))
        self.client.post(reverse('purchasing:supplier_price_update', args=[price.pk]), {
            'supplier': self.supplier.pk, 'product': self.product.pk,
            'unit_cost': '150.00', 'currency': 'PHP', 'lead_time_days': '',
            'valid_from': '', 'valid_to': '', 'is_active': True, 'notes': 'hike',
        })
        price.refresh_from_db()
        self.assertEqual(price.unit_cost, Decimal('150.00'))
        log = SupplierPriceLog.objects.get(price=price, previous_unit_cost=Decimal('100.00'))
        self.assertEqual(log.new_unit_cost, Decimal('150.00'))

    def test_no_change_does_not_log(self):
        price = SupplierPrice.objects.create(supplier=self.supplier, product=self.product, unit_cost=Decimal('100.00'))
        initial_logs = SupplierPriceLog.objects.filter(price=price).count()
        self.client.post(reverse('purchasing:supplier_price_update', args=[price.pk]), {
            'supplier': self.supplier.pk, 'product': self.product.pk,
            'unit_cost': '100.00', 'currency': 'PHP', 'lead_time_days': '',
            'valid_from': '', 'valid_to': '', 'is_active': True, 'notes': '',
        })
        self.assertEqual(SupplierPriceLog.objects.filter(price=price).count(), initial_logs)


class PriceListImportTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='pi_admin', password='x', role='admin')
        self.client.force_login(self.admin)

    def _make_csv(self, rows, headers=None):
        import csv as csv_mod
        import io
        if headers is None:
            headers = ['Supplier Name', 'Product SKU', 'Description', 'Unit Cost', 'Lead Time']
        buf = io.StringIO()
        writer = csv_mod.writer(buf)
        writer.writerow(headers)
        for r in rows:
            writer.writerow(r)
        return buf.getvalue().encode('utf-8')

    def test_csv_import_creates_supplier_product_price_and_publishes(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        data = self._make_csv([['Acme Co', 'SKU-X', 'Widget', '1,234.56', '10']])
        upload = SimpleUploadedFile('prices.csv', data, content_type='text/csv')
        resp = self.client.post(reverse('purchasing:pricelist_import'), {
            'file': upload, 'currency': 'PHP', 'notes': 'v1',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Supplier.objects.filter(name='Acme Co').exists())
        self.assertTrue(Product.objects.filter(sku='SKU-X').exists())
        price = SupplierPrice.objects.get(supplier__name='Acme Co', product__sku='SKU-X')
        self.assertEqual(price.unit_cost, Decimal('1234.56'))
        self.assertEqual(price.lead_time_days, 10)
        self.assertTrue(SupplierPriceLog.objects.filter(price=price).exists())
        # File published to company shared folder.
        self.assertTrue(CompanyFileShare.objects.filter(uploaded_by=self.admin).exists())

    def test_import_updates_existing_price(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        supplier = Supplier.objects.create(name='Acme Co')
        product = Product.objects.create(sku='SKU-X', description='Widget')
        SupplierPrice.objects.create(supplier=supplier, product=product, unit_cost=Decimal('100.00'))

        data = self._make_csv([['Acme Co', 'SKU-X', 'Widget', '200.00', '5']])
        upload = SimpleUploadedFile('prices.csv', data, content_type='text/csv')
        self.client.post(reverse('purchasing:pricelist_import'), {'file': upload, 'currency': 'PHP'})

        price = SupplierPrice.objects.get(supplier=supplier, product=product)
        self.assertEqual(price.unit_cost, Decimal('200.00'))
        self.assertEqual(price.lead_time_days, 5)
        self.assertEqual(
            SupplierPriceLog.objects.filter(price=price, previous_unit_cost=Decimal('100.00')).count(), 1
        )

    def test_import_skips_rows_missing_required_fields(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        # Missing Unit Cost on the second row.
        data = self._make_csv([
            ['Acme Co', 'SKU-1', 'Widget', '100.00', '5'],
            ['Acme Co', 'SKU-2', 'Widget2', '', '5'],
        ])
        upload = SimpleUploadedFile('prices.csv', data, content_type='text/csv')
        self.client.post(reverse('purchasing:pricelist_import'), {'file': upload, 'currency': 'PHP'})
        self.assertEqual(SupplierPrice.objects.count(), 1)
