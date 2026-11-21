from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from customers.models import Customer
from sales_funnel.models import SalesFunnel
from users.models import User


class ClosedDealCustomerEngagementTests(TestCase):
    def test_closing_deal_clears_only_automatic_inactivity(self):
        admin = User.objects.create_user(
            username='deal_status_admin',
            password='pass',
            role='admin',
        )
        salesperson = User.objects.create_user(
            username='deal_status_seller',
            password='pass',
            role='salesperson',
        )
        customer = Customer.objects.create(
            company_name='Manual Inactive Deal Customer',
            contact_person_name='Contact',
            email='manual-inactive-deal@example.test',
            salesperson=salesperson,
            is_active=False,
            auto_inactive_flag=True,
        )
        deal = SalesFunnel.objects.create(
            date_created=timezone.localdate(),
            company_name=customer.company_name,
            requirement_description='Customer purchase',
            cost=Decimal('10000.00'),
            retail=Decimal('15000.00'),
            stage='closable',
            salesperson=salesperson,
            customer=customer,
        )

        self.client.force_login(admin)
        response = self.client.post(
            reverse('sales_funnel:close_entry', args=[deal.pk]),
            {'won': 'true'},
        )

        self.assertEqual(response.status_code, 302)
        customer.refresh_from_db()
        self.assertFalse(customer.auto_inactive_flag)
        self.assertFalse(customer.is_active)
        self.assertTrue(
            customer.history.filter(
                action='field_updated',
                user_agent='system/customer_engagement',
            ).exists()
        )
