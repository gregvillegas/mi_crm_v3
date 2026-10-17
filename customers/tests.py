from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
import csv
import io

from customers.models import Customer, CustomerContact
from users.models import User


class CustomerImportTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_user',
            password='testpass123',
            role='admin',
            email='admin@example.com',
        )
        self.salesperson = User.objects.create_user(
            username='jds',
            password='testpass123',
            role='salesperson',
            email='jds@example.com',
            initials='JDS',
        )
        self.client.force_login(self.admin)

    def test_import_customers_with_contacts_creates_customer_and_related_contacts(self):
        csv_content = (
            'company_name,contact_person_name,contact_person_position,email,phone_number,address,industry,territory,active_status,salesperson_initials,'
            'contact_2_name,contact_2_position,contact_2_email,contact_2_phone,contact_2_is_primary,'
            'contact_3_name,contact_3_position,contact_3_email,contact_3_phone,contact_3_is_primary\n'
            'ABC Corporation,John Doe,CEO,john.doe@abccorp.com,+1234567890,"123 Main St, Makati City",Technology,Makati City,Yes,JDS,'
            'Maria Santos,Procurement Manager,maria.santos@abccorp.com,+639171112233,No,'
            'Peter Cruz,IT Manager,peter.cruz@abccorp.com,+639181234567,Yes\n'
        )
        upload = SimpleUploadedFile(
            'customer_with_contacts.csv',
            csv_content.encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            reverse('import_customers_with_contacts'),
            {'csv_file': upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        customer = Customer.objects.get(email='john.doe@abccorp.com')
        self.assertEqual(customer.company_name, 'ABC Corporation')
        self.assertEqual(customer.salesperson, self.salesperson)
        self.assertEqual(customer.contacts.count(), 2)
        self.assertTrue(customer.contacts.filter(email='peter.cruz@abccorp.com', is_primary=True).exists())

    def test_legacy_import_customers_still_creates_only_customer_row(self):
        csv_content = (
            'Company Name,Contact Person Name,Contact Person Position,Email,Phone Number,Address,Industry,Territory,Millionaire Status,Active Status,Salesperson Initials,Created At,Updated At\n'
            'XYZ Industries,Jane Smith,Purchasing Manager,jane.smith@xyzind.com,+0987654321,"456 Oak Ave, Pasig City",Manufacturing,Pasig City,No,Yes,JDS,,\n'
        )
        upload = SimpleUploadedFile(
            'customer_legacy.csv',
            csv_content.encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            reverse('import_customers'),
            {'csv_file': upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        customer = Customer.objects.get(email='jane.smith@xyzind.com')
        self.assertEqual(customer.company_name, 'XYZ Industries')
        self.assertEqual(customer.contacts.count(), 0)
        self.assertEqual(CustomerContact.objects.count(), 0)

    def test_legacy_import_customers_updates_existing_customer_by_company_and_email(self):
        Customer.objects.create(
            company_name='Old Company',
            contact_person_name='Old Contact',
            contact_person_position='Old Position',
            email='dup@customer.com',
            phone_number='',
            address='',
            industry='',
            territory='',
            is_active=True,
            salesperson=self.salesperson,
        )

        csv_content = (
            'Company Name,Contact Person Name,Contact Person Position,Email,Phone Number,Address,Industry,Territory,Millionaire Status,Active Status,Salesperson Initials,Created At,Updated At\n'
            'Old Company,New Contact,New Position,dup@customer.com,+639000000000,"New Address",Technology,Makati City,No,No,JDS,,\n'
        )
        upload = SimpleUploadedFile(
            'customer_update_existing.csv',
            csv_content.encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            reverse('import_customers'),
            {'csv_file': upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        customer = Customer.objects.get(email='dup@customer.com', company_name='Old Company')
        self.assertEqual(customer.company_name, 'Old Company')
        self.assertEqual(customer.contact_person_name, 'New Contact')
        self.assertEqual(customer.contact_person_position, 'New Position')
        self.assertEqual(customer.phone_number, '+639000000000')
        self.assertEqual(customer.territory, 'makati')
        self.assertFalse(customer.is_active)

        messages = [message.message for message in get_messages(response.wsgi_request)]
        combined_message = '\n'.join(messages)
        self.assertIn('Created: 0. Updated: 1.', combined_message)
        self.assertNotIn('already exists', combined_message)

    def test_legacy_import_customers_allows_duplicate_email_across_companies(self):
        csv_content = (
            'Company Name,Contact Person Name,Contact Person Position,Email,Phone Number,Address,Industry,Territory,Millionaire Status,Active Status,Salesperson Initials,Created At,Updated At\n'
            'Herma Corporation,Justine Morillo,Procurement,shared.it@herma.com.ph,+639111111111,"Makati",Technology,Makati City,No,Yes,JDS,,\n'
            'Herma Shipping and Transport Corporation,Justine Morillo,Procurement,shared.it@herma.com.ph,+639222222222,"Pasig",Technology,Pasig City,No,Yes,JDS,,\n'
        )
        upload = SimpleUploadedFile(
            'duplicate_email_multiple_companies.csv',
            csv_content.encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            reverse('import_customers'),
            {'csv_file': upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Customer.objects.filter(email='shared.it@herma.com.ph').count(), 2)
        self.assertTrue(
            Customer.objects.filter(
                email='shared.it@herma.com.ph',
                company_name='Herma Corporation',
            ).exists()
        )
        self.assertTrue(
            Customer.objects.filter(
                email='shared.it@herma.com.ph',
                company_name='Herma Shipping and Transport Corporation',
            ).exists()
        )

    def test_export_customers_with_contacts_matches_single_file_import_shape(self):
        customer = Customer.objects.create(
            company_name='ABC Corporation',
            contact_person_name='John Doe',
            contact_person_position='CEO',
            email='john.doe@abccorp.com',
            phone_number='+1234567890',
            address='123 Main St, Makati City',
            industry='technology',
            territory='makati',
            is_active=True,
            salesperson=self.salesperson,
        )
        CustomerContact.objects.create(
            customer=customer,
            name='Maria Santos',
            position='Procurement Manager',
            email='maria.santos@abccorp.com',
            phone='+639171112233',
            is_primary=False,
        )
        CustomerContact.objects.create(
            customer=customer,
            name='Peter Cruz',
            position='IT Manager',
            email='peter.cruz@abccorp.com',
            phone='+639181234567',
            is_primary=True,
        )

        response = self.client.get(reverse('export_customers_with_contacts'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        reader = csv.reader(io.StringIO(response.content.decode('utf-8')))
        rows = list(reader)

        self.assertEqual(rows[0][0:10], [
            'company_name',
            'contact_person_name',
            'contact_person_position',
            'email',
            'phone_number',
            'address',
            'industry',
            'territory',
            'active_status',
            'salesperson_initials',
        ])
        self.assertEqual(rows[1][0], 'ABC Corporation')
        self.assertEqual(rows[1][1], 'John Doe')
        self.assertEqual(rows[1][3], 'john.doe@abccorp.com')
        self.assertEqual(rows[1][9], 'JDS')
        self.assertIn('Maria Santos', rows[1])
        self.assertIn('Peter Cruz', rows[1])
        self.assertIn('Yes', rows[1])

    def test_import_customers_with_contacts_shows_detected_headers_on_required_field_mismatch(self):
        csv_content = (
            'company,primary_contact_name,primary_contact_position,primary_email,phone_number,address,industry,territory,active_status,salesperson_initials\n'
            'Toy Maker Corporation,Jim Doe,CEO,jim.doe@toymaker.com,1234567890,"123 Main St, Makati City",Technology,Makati City,Yes,JDS\n'
        )
        upload = SimpleUploadedFile(
            'customer_header_mismatch.csv',
            csv_content.encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            reverse('import_customers_with_contacts'),
            {'csv_file': upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        messages = [message.message for message in get_messages(response.wsgi_request)]
        warning_message = '\n'.join(messages)
        self.assertIn('Detected headers:', warning_message)
        self.assertIn('primary_email', warning_message)
        self.assertIn('Normalized headers:', warning_message)

    def test_import_customer_contacts_rejects_customer_import_csv_shape(self):
        csv_content = (
            'company_name,contact_person_name,contact_person_position,email,phone_number,address,industry,territory,active_status,salesperson_initials,'
            'contact_2_name,contact_2_position,contact_2_email,contact_2_phone,contact_2_is_primary\n'
            'Toy Maker Corporation,Jim Doe,CEO,jim.doe@toymaker.com,1234567890,"123 Main St, Makati City",Technology,Makati City,Yes,JDS,'
            'Anna Santos,Procurement Manager,anna.santos@toymaker.com,+639171111111,No\n'
        )
        upload = SimpleUploadedFile(
            'contacts_wrong_shape.csv',
            csv_content.encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            reverse('import_customer_contacts'),
            {'csv_file': upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(CustomerContact.objects.count(), 0)

        messages = [message.message for message in get_messages(response.wsgi_request)]
        error_message = '\n'.join(messages)
        self.assertIn('customer import CSV, not a contacts-only CSV', error_message)
        self.assertIn('Import Customers + Contacts', error_message)
        self.assertIn('Detected headers:', error_message)
        self.assertIn('Normalized headers:', error_message)
    def test_legacy_import_customers_accepts_territory_with_city_suffix(self):
        csv_content = (
            'Company Name,Contact Person Name,Contact Person Position,Email,Phone Number,Address,Industry,Territory,Millionaire Status,Active Status,Salesperson Initials,Created At,Updated At\n'
            'North Metro Supplies,Juan Dela Cruz,Buyer,juan@northmetro.com,+639111111111,"Makati Ave, Makati City",Technology,Makati City,No,Yes,JDS,,\n'
            'East Trade Corp,Ana Reyes,Manager,ana@easttrade.com,+639222222222,"Ortigas, Pasig City",Manufacturing,Pasig City,No,Yes,JDS,,\n'
        )
        upload = SimpleUploadedFile(
            'territory_city_suffix.csv',
            csv_content.encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            reverse('import_customers'),
            {'csv_file': upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Customer.objects.filter(email='juan@northmetro.com', territory='makati').count(), 1)
        self.assertEqual(Customer.objects.filter(email='ana@easttrade.com', territory='pasig').count(), 1)

        messages = [message.message for message in get_messages(response.wsgi_request)]
        combined_message = '\n'.join(messages)
        self.assertIn('Successfully processed customers. Created: 2. Updated: 0.', combined_message)
        self.assertNotIn('Invalid territory', combined_message)

    def test_legacy_import_customers_rejects_contacts_only_csv_shape(self):
        csv_content = (
            'customer_email,contact_name,contact_position,contact_email,contact_phone,is_primary\n'
            'john.doe@abccorp.com,Maria Santos,Procurement Manager,maria.santos@abccorp.com,+639171112233,Yes\n'
            'john.doe@abccorp.com,Peter Cruz,IT Manager,peter.cruz@abccorp.com,+639181234567,No\n'
        )
        upload = SimpleUploadedFile(
            'contacts_only_wrong_import.csv',
            csv_content.encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            reverse('import_customers'),
            {'csv_file': upload},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Customer.objects.filter(company_name='john.doe@abccorp.com').count(),
            0,
        )
        self.assertEqual(
            Customer.objects.filter(contact_person_name='Maria Santos').count(),
            0,
        )

        messages = [message.message for message in get_messages(response.wsgi_request)]
        error_message = '\n'.join(messages)
        self.assertIn('contacts-only CSV, not a customer import CSV', error_message)
        self.assertIn('Use Import Contacts instead', error_message)
        self.assertIn('Detected headers:', error_message)
        self.assertIn('Normalized headers:', error_message)


class CustomerExportFilterTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_export',
            password='testpass123',
            role='admin',
            email='admin.export@example.com',
        )
        self.client.force_login(self.admin)

        Customer.objects.create(
            company_name='BPO Millionaire Corp',
            contact_person_name='Alice',
            email='alice@bpo-millionaire.com',
            industry='business',
            territory='makati',
            is_millionaire_account=True,
            is_active=True,
        )
        Customer.objects.create(
            company_name='BPO Regular Corp',
            contact_person_name='Bob',
            email='bob@bpo-regular.com',
            industry='business',
            territory='pasig',
            is_millionaire_account=False,
            is_active=True,
        )
        Customer.objects.create(
            company_name='Manufacturing Millionaire Corp',
            contact_person_name='Carol',
            email='carol@manufacturing-millionaire.com',
            industry='manufacturing',
            territory='makati',
            is_millionaire_account=True,
            is_active=True,
        )

    def test_export_customers_respects_dashboard_filters(self):
        response = self.client.get(reverse('export_customers'), {
            'industry': 'business',
            'millionaire': 'yes',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')

        csv_text = response.content.decode('utf-8')
        self.assertIn('BPO Millionaire Corp', csv_text)
        self.assertNotIn('BPO Regular Corp', csv_text)
        self.assertNotIn('Manufacturing Millionaire Corp', csv_text)
