from django.test import TestCase
from django.urls import reverse

from customers.models import Customer
from users.models import User


class CustomerDashboardCardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='customer_card_admin',
            password='pass',
            role='admin',
        )
        self.client.force_login(self.admin)

        Customer.objects.create(
            company_name='Auto Inactive Customer',
            contact_person_name='Contact',
            email='auto-inactive@example.test',
            is_active=True,
            auto_inactive_flag=True,
        )
        Customer.objects.create(
            company_name='Manual Inactive Customer',
            contact_person_name='Contact',
            email='manual-inactive@example.test',
            is_active=False,
            auto_inactive_flag=False,
        )
        Customer.objects.create(
            company_name='Active Customer',
            contact_person_name='Contact',
            email='active@example.test',
            is_active=True,
            auto_inactive_flag=False,
        )
        Customer.objects.create(
            company_name='Millionaire Customer',
            contact_person_name='Contact',
            email='millionaire@example.test',
            is_active=True,
            auto_inactive_flag=False,
            is_millionaire_account=True,
        )

    @staticmethod
    def customer_names(response):
        return {customer.company_name for customer in response.context['customers']}

    def test_status_and_millionaire_cards_link_to_filtered_customer_lists(self):
        response = self.client.get(reverse('customer_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{reverse("customer_list")}?status=inactive"')
        self.assertContains(response, f'href="{reverse("customer_list")}?millionaire=yes"')
        self.assertContains(response, f'href="{reverse("customer_list")}?status=active"')

    def test_inactive_and_active_card_filters_match_dashboard_status_rules(self):
        inactive_response = self.client.get(
            reverse('customer_list'),
            {'status': 'inactive'},
        )
        active_response = self.client.get(
            reverse('customer_list'),
            {'status': 'active'},
        )

        self.assertEqual(
            self.customer_names(inactive_response),
            {'Auto Inactive Customer', 'Manual Inactive Customer'},
        )
        self.assertEqual(
            self.customer_names(active_response),
            {'Active Customer', 'Millionaire Customer'},
        )

    def test_millionaire_card_filter_returns_only_millionaire_accounts(self):
        response = self.client.get(
            reverse('customer_list'),
            {'millionaire': 'yes'},
        )

        self.assertEqual(self.customer_names(response), {'Millionaire Customer'})
