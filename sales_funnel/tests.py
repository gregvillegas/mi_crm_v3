import csv
import io
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.management import call_command

from customers.models import Customer
from sales_funnel.models import SalesFunnel
from sales_proposals.models import Proposal, ProposalItem
from users.models import User


class SalesFunnelDashboardFilterTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_sf',
            password='testpass123',
            role='admin',
            email='admin_sf@example.com',
        )
        self.salesperson = User.objects.create_user(
            username='seller_sf',
            password='testpass123',
            role='salesperson',
            email='seller_sf@example.com',
            initials='SFS',
        )
        self.client.force_login(self.admin)

        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())

        SalesFunnel.objects.create(
            date_created=week_start,
            company_name='Alpha Network Systems',
            brand='Cisco',
            requirement_description='Network refresh',
            cost=Decimal('100000.00'),
            retail=Decimal('150000.00'),
            stage='quoted',
            salesperson=self.salesperson,
            probability=50,
        )
        SalesFunnel.objects.create(
            date_created=week_start + timedelta(days=1),
            company_name='Beta Enterprise Solutions',
            brand='IBM',
            requirement_description='Server modernization',
            cost=Decimal('200000.00'),
            retail=Decimal('300000.00'),
            stage='quoted',
            salesperson=self.salesperson,
            probability=60,
        )
        SalesFunnel.objects.create(
            date_created=week_start - timedelta(days=7),
            company_name='Old Quoted Co',
            brand='OldBrand',
            requirement_description='Old quote',
            cost=Decimal('1000.00'),
            retail=Decimal('2000.00'),
            stage='quoted',
            salesperson=self.salesperson,
            probability=50,
        )

    def test_dashboard_brand_filter_supports_typeable_partial_match(self):
        response = self.client.get(
            reverse('sales_funnel:dashboard'),
            {'brand': 'cis'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alpha Network Systems')
        self.assertNotContains(response, 'Beta Enterprise Solutions')
        self.assertContains(response, 'value="Cisco"', html=False)

    def test_export_uses_brand_filter_and_includes_brand_column(self):
        response = self.client.get(
            reverse('sales_funnel:export'),
            {'brand': 'ibm'},
        )

        self.assertEqual(response.status_code, 200)
        reader = csv.reader(io.StringIO(response.content.decode('utf-8')))
        rows = list(reader)

        self.assertEqual(rows[0][0:4], ['Date', 'Company', 'Brand', 'Stage'])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][1], 'Beta Enterprise Solutions')
        self.assertEqual(rows[1][2], 'IBM')

    def test_dashboard_uses_linked_proposal_quoted_totals_for_optional_items(self):
        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        customer = Customer.objects.create(
            company_name='Gamma Holdings',
            contact_person_name='Gina Buyer',
            email='gina@gamma.test',
            salesperson=self.salesperson,
        )
        proposal = Proposal.objects.create(
            customer=customer,
            created_by=self.salesperson,
            subject='Server Cluster',
        )
        ProposalItem.objects.create(
            proposal=proposal,
            part_number='REQ-500',
            description='Required node',
            quantity=Decimal('1'),
            unit_cost=Decimal('20000.00'),
            unit_price=Decimal('30000.00'),
        )
        ProposalItem.objects.create(
            proposal=proposal,
            part_number='OPT-500',
            description='Optional storage',
            quantity=Decimal('1'),
            unit_cost=Decimal('10000.00'),
            unit_price=Decimal('15000.00'),
            is_optional=True,
        )
        proposal.calculate_totals()

        SalesFunnel.objects.create(
            date_created=week_start + timedelta(days=2),
            company_name='Gamma Holdings',
            brand='Dell',
            requirement_description='Server Cluster',
            cost=Decimal('0.00'),
            retail=Decimal('0.00'),
            stage='quoted',
            salesperson=self.salesperson,
            customer=customer,
            proposal=proposal,
            probability=70,
        )

        response = self.client.get(reverse('sales_funnel:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Gamma Holdings')
        self.assertContains(response, '45,000.00')
        self.assertContains(response, '15,000.00')

    def test_dashboard_pink_funnel_only_shows_current_week(self):
        response = self.client.get(reverse('sales_funnel:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alpha Network Systems')
        self.assertContains(response, 'Beta Enterprise Solutions')
        self.assertNotContains(response, 'Old Quoted Co')

    def test_table_view_shows_account_manager_header_and_proposal_reference(self):
        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())

        customer = Customer.objects.create(
            company_name='Proposal Link Co',
            contact_person_name='Pol Buyer',
            email='pol@link.test',
            salesperson=self.salesperson,
        )
        proposal = Proposal.objects.create(
            customer=customer,
            created_by=self.salesperson,
            subject='Linked Proposal',
            reference_number='REF20260523001',
        )
        SalesFunnel.objects.create(
            date_created=week_start,
            company_name='Proposal Link Co',
            brand='HP',
            requirement_description='Linked funnel entry',
            cost=Decimal('0.00'),
            retail=Decimal('0.00'),
            stage='quoted',
            salesperson=self.salesperson,
            customer=customer,
            proposal=proposal,
            probability=50,
        )
        SalesFunnel.objects.create(
            date_created=week_start,
            company_name='No Proposal Co',
            brand='HP',
            requirement_description='Unlinked funnel entry',
            cost=Decimal('0.00'),
            retail=Decimal('0.00'),
            stage='quoted',
            salesperson=self.salesperson,
            probability=50,
        )

        response = self.client.get(reverse('sales_funnel:dashboard'), {'view': 'table'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '>Account Manager<', html=False)
        self.assertContains(response, '>Ref #<', html=False)
        self.assertContains(response, 'REF20260523001')
        proposal_url = reverse('proposal_detail', args=[proposal.pk])
        self.assertContains(response, f'href="{proposal_url}"', html=False)
        self.assertNotContains(response, '>No Proposal Co</a>', html=False)

    def test_table_view_uses_am_header_for_salesperson(self):
        self.client.force_login(self.salesperson)
        response = self.client.get(reverse('sales_funnel:dashboard'), {'view': 'table'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '>AM<', html=False)
        self.assertNotContains(response, '>SP<', html=False)


class SalesFunnelPromotionCommandTests(TestCase):
    def test_promote_quoted_funnel_moves_entries_based_on_retail_threshold(self):
        admin = User.objects.create_user(
            username='admin_sf_promote',
            password='testpass123',
            role='admin',
            email='admin_sf_promote@example.com',
        )
        salesperson = User.objects.create_user(
            username='seller_sf_promote',
            password='testpass123',
            role='salesperson',
            email='seller_sf_promote@example.com',
            initials='SFP',
        )
        self.client.force_login(admin)

        today = date(2026, 5, 23)
        week_start = today - timedelta(days=today.weekday())
        older_date = week_start - timedelta(days=1)

        green = SalesFunnel.objects.create(
            date_created=older_date,
            company_name='Promote Green Co',
            brand='Cisco',
            requirement_description='Old quote high value',
            cost=Decimal('100.00'),
            retail=Decimal('500000.00'),
            stage='quoted',
            salesperson=salesperson,
            probability=50,
        )
        blue = SalesFunnel.objects.create(
            date_created=older_date,
            company_name='Promote Blue Co',
            brand='Dell',
            requirement_description='Old quote low value',
            cost=Decimal('100.00'),
            retail=Decimal('499999.99'),
            stage='quoted',
            salesperson=salesperson,
            probability=50,
        )
        keep = SalesFunnel.objects.create(
            date_created=week_start,
            company_name='Keep Pink Co',
            brand='IBM',
            requirement_description='This week quote',
            cost=Decimal('100.00'),
            retail=Decimal('600000.00'),
            stage='quoted',
            salesperson=salesperson,
            probability=50,
        )

        call_command('promote_quoted_funnel', today='2026-05-23')

        green.refresh_from_db()
        blue.refresh_from_db()
        keep.refresh_from_db()

        self.assertEqual(green.stage, 'project')
        self.assertEqual(blue.stage, 'services')
        self.assertEqual(keep.stage, 'quoted')


class SalesFunnelDealsHistoryTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_deals',
            password='testpass123',
            role='admin',
            email='admin_deals@example.com',
        )
        self.seller_one = User.objects.create_user(
            username='seller_one',
            password='testpass123',
            role='salesperson',
            email='seller_one@example.com',
            initials='ONE',
        )
        self.seller_two = User.objects.create_user(
            username='seller_two',
            password='testpass123',
            role='salesperson',
            email='seller_two@example.com',
            initials='TWO',
        )
        self.customer = Customer.objects.create(
            company_name='Deals History Corp',
            contact_person_name='Helen Buyer',
            email='helen@deals.test',
            salesperson=self.seller_one,
        )
        self.client.force_login(self.admin)

        SalesFunnel.objects.create(
            date_created=date(2026, 10, 1),
            company_name='Won Deal One',
            brand='Cisco',
            requirement_description='Network core refresh',
            cost=Decimal('100000.00'),
            retail=Decimal('150000.00'),
            salesperson=self.seller_one,
            customer=self.customer,
            is_closed=True,
            deal_outcome='won',
            closed_date=date(2026, 10, 5),
        )
        SalesFunnel.objects.create(
            date_created=date(2026, 10, 2),
            company_name='Won Deal Two',
            brand='HP',
            requirement_description='Desktop rollout',
            cost=Decimal('120000.00'),
            retail=Decimal('180000.00'),
            salesperson=self.seller_one,
            customer=self.customer,
            is_closed=True,
            deal_outcome='won',
            closed_date=date(2026, 10, 6),
        )
        SalesFunnel.objects.create(
            date_created=date(2026, 10, 3),
            company_name='Lost Deal One',
            brand='Dell',
            requirement_description='Server refresh',
            cost=Decimal('90000.00'),
            retail=Decimal('140000.00'),
            salesperson=self.seller_one,
            customer=self.customer,
            is_closed=True,
            deal_outcome='lost',
            lost_reason='Client stayed with incumbent supplier.',
            closed_date=date(2026, 10, 7),
        )
        SalesFunnel.objects.create(
            date_created=date(2026, 10, 4),
            company_name='Won Deal Three',
            brand='IBM',
            requirement_description='Storage expansion',
            cost=Decimal('110000.00'),
            retail=Decimal('170000.00'),
            salesperson=self.seller_two,
            customer=self.customer,
            is_closed=True,
            deal_outcome='won',
            closed_date=date(2026, 10, 8),
        )

    def test_deals_history_uses_overall_win_rate_not_last_salesperson_rate(self):
        response = self.client.get(reverse('sales_funnel:deals_history'))

        self.assertEqual(response.status_code, 200)
        self.assertAlmostEqual(response.context['win_rate'], 75.0)
        self.assertContains(response, '75.0%')

    def test_deals_history_cards_link_to_outcome_detail_pages(self):
        response = self.client.get(reverse('sales_funnel:deals_history'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('sales_funnel:closed_deals_detail', args=['won']))
        self.assertContains(response, reverse('sales_funnel:closed_deals_detail', args=['lost']))

    def test_lost_deals_detail_page_shows_reason_column_and_only_lost_entries(self):
        response = self.client.get(reverse('sales_funnel:closed_deals_detail', args=['lost']))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '>Reason<', html=False)
        self.assertContains(response, 'Lost Deal One')
        self.assertContains(response, 'Client stayed with incumbent supplier.')
        self.assertNotContains(response, 'Won Deal One')
