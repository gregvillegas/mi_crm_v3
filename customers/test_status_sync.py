from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from customers.models import Customer, CustomerHistory
from customers.status import clear_auto_inactive_for_engagement
from sales_funnel.models import SalesFunnel
from sales_monitoring.models import ActivityType, SalesActivity
from sales_proposals.models import Proposal, ProposalEmailLog
from users.models import User


class CustomerStatusSyncTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.salesperson = User.objects.create_user(
            username='status_seller',
            password='pass',
            role='salesperson',
        )
        self.activity_type = ActivityType.objects.create(name='Status Test Activity')

    def make_old_customer(self, company_name):
        customer = Customer.objects.create(
            company_name=company_name,
            contact_person_name='Customer Contact',
            email=f'{company_name.lower().replace(" ", "-")}@example.test',
            salesperson=self.salesperson,
        )
        Customer.objects.filter(pk=customer.pk).update(
            created_at=self.now - timedelta(days=120),
        )
        customer.refresh_from_db()
        return customer

    def sync_customer(self, customer):
        call_command('sync_customer_status_flags', customer_id=customer.pk, verbosity=0)
        customer.refresh_from_db()
        return customer

    def test_only_completed_sales_activities_reset_inactivity_clock(self):
        customer = self.make_old_customer('Planned Activity Co')
        planned = SalesActivity.objects.create(
            title='Future visit',
            activity_type=self.activity_type,
            salesperson=self.salesperson,
            customer=customer,
            status='planned',
        )

        self.assertTrue(self.sync_customer(customer).auto_inactive_flag)
        self.assertIsNone(customer.last_sales_activity_at)

        planned.status = 'completed'
        planned.actual_end = self.now - timedelta(days=10)
        planned.save()
        self.assertFalse(self.sync_customer(customer).auto_inactive_flag)
        self.assertEqual(customer.last_sales_activity_at, planned.actual_end)

    def test_successful_proposal_send_counts_but_failed_send_does_not(self):
        failed_customer = self.make_old_customer('Failed Proposal Co')
        failed_proposal = Proposal.objects.create(
            customer=failed_customer,
            created_by=self.salesperson,
            subject='Failed proposal',
        )
        ProposalEmailLog.objects.create(
            proposal=failed_proposal,
            sent_by=self.salesperson,
            recipients=failed_customer.email,
            status='failed',
            error_message='Delivery rejected',
        )
        self.assertTrue(self.sync_customer(failed_customer).auto_inactive_flag)

        sent_customer = self.make_old_customer('Sent Proposal Co')
        sent_proposal = Proposal.objects.create(
            customer=sent_customer,
            created_by=self.salesperson,
            subject='Successful proposal',
        )
        ProposalEmailLog.objects.create(
            proposal=sent_proposal,
            sent_by=self.salesperson,
            recipients=sent_customer.email,
            status='sent',
        )
        self.assertFalse(self.sync_customer(sent_customer).auto_inactive_flag)

    def test_recent_won_deal_resets_clock_and_won_revenue(self):
        customer = self.make_old_customer('Won Deal Co')
        SalesFunnel.objects.create(
            date_created=(self.now - timedelta(days=20)).date(),
            company_name=customer.company_name,
            requirement_description='Closed customer deal',
            cost=Decimal('800000.00'),
            retail=Decimal('1200000.00'),
            stage='closable',
            salesperson=self.salesperson,
            customer=customer,
            deal_outcome='won',
            is_closed=True,
            closed_date=(self.now - timedelta(days=10)).date(),
        )

        customer = self.sync_customer(customer)
        self.assertFalse(customer.auto_inactive_flag)
        self.assertTrue(customer.is_millionaire_account)
        self.assertEqual(customer.lifetime_won_revenue, Decimal('1200000.00'))

    def test_recent_closed_lost_deal_counts_as_engagement(self):
        customer = self.make_old_customer('Lost Deal Co')
        SalesFunnel.objects.create(
            date_created=(self.now - timedelta(days=20)).date(),
            company_name=customer.company_name,
            requirement_description='Closed lost deal',
            cost=Decimal('10000.00'),
            retail=Decimal('20000.00'),
            stage='closable',
            salesperson=self.salesperson,
            customer=customer,
            deal_outcome='lost',
            is_closed=True,
            closed_date=(self.now - timedelta(days=10)).date(),
        )

        self.assertFalse(self.sync_customer(customer).auto_inactive_flag)

    def test_salesperson_reassignment_does_not_reset_inactivity_clock(self):
        customer = self.make_old_customer('Reassigned Co')
        history = CustomerHistory.objects.create(
            customer=customer,
            action='salesperson_assigned',
            description='Recently assigned to a salesperson',
            changed_by=self.salesperson,
        )
        CustomerHistory.objects.filter(pk=history.pk).update(
            timestamp=self.now - timedelta(days=5),
        )

        self.assertTrue(self.sync_customer(customer).auto_inactive_flag)

    def test_engagement_clears_auto_flag_without_overriding_manual_inactive(self):
        customer = self.make_old_customer('Manual Inactive Co')
        customer.is_active = False
        customer.auto_inactive_flag = True
        customer.save(update_fields=['is_active', 'auto_inactive_flag'])

        cleared = clear_auto_inactive_for_engagement(
            customer,
            source='a completed sales activity',
            changed_by=self.salesperson,
        )

        customer.refresh_from_db()
        self.assertTrue(cleared)
        self.assertFalse(customer.auto_inactive_flag)
        self.assertFalse(customer.is_active)
        self.assertTrue(
            customer.history.filter(user_agent='system/customer_engagement').exists()
        )
