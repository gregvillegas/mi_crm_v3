from django.test import TestCase

from customers.models import Customer
from sales_monitoring.models import SalesActivity
from sales_proposals.models import Proposal
from sales_proposals.views import log_sales_activity, update_sales_funnel
from users.models import User


class ProposalActivityLifecycleTests(TestCase):
    def setUp(self):
        self.salesperson = User.objects.create_user(
            username='proposal_status_seller',
            password='pass',
            role='salesperson',
        )
        self.customer = Customer.objects.create(
            company_name='Proposal Engagement Customer',
            contact_person_name='Contact',
            email='proposal-engagement@example.test',
            salesperson=self.salesperson,
            auto_inactive_flag=True,
        )
        self.proposal = Proposal.objects.create(
            customer=self.customer,
            created_by=self.salesperson,
            subject='Customer proposal',
        )

    def _activities(self):
        return SalesActivity.objects.filter(proposal=self.proposal)

    def test_unsent_proposal_shows_ongoing_activity_without_clearing_auto_flag(self):
        log_sales_activity(self.proposal, self.salesperson)

        self.customer.refresh_from_db()
        activity = self._activities().get()
        self.assertEqual(activity.status, 'in_progress')
        self.assertTrue(activity.title.startswith('Proposal Created:'))
        self.assertEqual(activity.customer, self.customer)
        # A draft is not engagement, so the inactivity clock must not reset.
        self.assertTrue(self.customer.auto_inactive_flag)

    def test_pending_approval_is_named_in_the_description(self):
        self.proposal.approval_required = True
        self.proposal.approval_status = 'pending'
        self.proposal.save()

        log_sales_activity(self.proposal, self.salesperson)

        self.assertIn('pending', self._activities().get().description)

    def test_send_flips_the_same_row_to_completed_and_clears_auto_flag(self):
        log_sales_activity(self.proposal, self.salesperson)

        self.proposal.status = 'sent'
        self.proposal.save()
        log_sales_activity(self.proposal, self.salesperson)

        self.customer.refresh_from_db()
        self.assertEqual(self._activities().count(), 1)
        activity = self._activities().get()
        self.assertEqual(activity.status, 'completed')
        self.assertEqual(activity.title, f'Sent Proposal: {self.proposal.proposal_number}')
        self.assertFalse(self.customer.auto_inactive_flag)
        self.assertTrue(
            self.customer.history.filter(
                action='field_updated',
                user_agent='system/customer_engagement',
            ).exists()
        )

    def test_repeated_sync_keeps_a_single_activity_row(self):
        log_sales_activity(self.proposal, self.salesperson)
        log_sales_activity(self.proposal, self.salesperson)

        self.assertEqual(self._activities().count(), 1)

    def test_update_sales_funnel_creates_the_ongoing_activity(self):
        update_sales_funnel(self.proposal)

        activity = self._activities().get()
        self.assertEqual(activity.status, 'in_progress')
        self.assertEqual(activity.salesperson, self.salesperson)

    def test_test_proposals_do_not_create_activities(self):
        self.proposal.is_test = True
        self.proposal.save()

        log_sales_activity(self.proposal, self.salesperson)

        self.assertEqual(self._activities().count(), 0)
