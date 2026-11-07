from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse

from customers.models import Customer
from customers.permissions import visible_customers_queryset
from sales_funnel.models import SalesFunnel
from sales_proposals.models import Proposal, ProposalItem
from sales_proposals.views import update_sales_funnel, visible_proposals_queryset
from teams.models import (
    Group,
    Team,
    TeamMembership,
    tech_manager_team_ids,
    technical_sales_team_ids,
    technical_sales_users_for_teams,
)
from users.models import User


class TechnicalSalesScopingTests(TestCase):
    """
    Covers the Technical Sales role added by docs/TECHNICAL_SALES_ROLE_PLAN.md:
    team scoping, customer/proposal visibility, the TS -> Technical Manager
    approval rule (including the "mastered" exemption) and auto-funnel credit.
    """

    def setUp(self):
        password = 'testpass123'
        self.avp = User.objects.create_user(
            username='avp_ts', password=password, role='avp', email='avp_ts@example.com',
        )
        self.asm = User.objects.create_user(
            username='asm_ts', password=password, role='asm', email='asm_ts@example.com',
        )
        self.supervisor = User.objects.create_user(
            username='sup_ts', password=password, role='supervisor', email='sup_ts@example.com',
        )

        # One Technical Manager per team (two teams => two managers).
        self.techmgr_a = User.objects.create_user(
            username='techmgr_a', password=password, role='techmgr', email='techmgr_a@example.com',
        )
        self.techmgr_b = User.objects.create_user(
            username='techmgr_b', password=password, role='techmgr', email='techmgr_b@example.com',
        )

        self.team_a = Team.objects.create(
            name='Alpha Team', avp=self.avp, asm=self.asm, tech_manager=self.techmgr_a,
        )
        self.team_b = Team.objects.create(
            name='Bravo Team', avp=self.avp, asm=self.asm, tech_manager=self.techmgr_b,
        )
        self.group_a = Group.objects.create(name='Alpha Group', team=self.team_a, supervisor=self.supervisor)
        self.group_b = Group.objects.create(name='Bravo Group', team=self.team_b, supervisor=self.supervisor)

        # Account managers (salespeople) who own the customers in each team.
        self.seller_a = User.objects.create_user(
            username='seller_a', password=password, role='salesperson', email='seller_a@example.com', initials='SLA',
        )
        self.seller_b = User.objects.create_user(
            username='seller_b', password=password, role='salesperson', email='seller_b@example.com', initials='SLB',
        )
        TeamMembership.objects.create(user=self.seller_a, group=self.group_a)
        TeamMembership.objects.create(user=self.seller_b, group=self.group_b)

        self.customer_a = Customer.objects.create(
            company_name='Alpha Customer', contact_person_name='Al Buyer',
            email='al@alpha.test', salesperson=self.seller_a,
        )
        self.customer_b = Customer.objects.create(
            company_name='Bravo Customer', contact_person_name='Bea Buyer',
            email='bea@bravo.test', salesperson=self.seller_b,
        )

        # The three Technical Sales shapes from the plan:
        #   ts_solo -> single person handling every technical team (flagged)
        #   ts_a / ts_b -> two people, one attached per team
        #   ts_none -> nobody attached yet (must see nothing)
        self.ts_solo = User.objects.create_user(
            username='ts_solo', password=password, role='technical_sales',
            email='ts_solo@example.com', initials='TSS', handles_all_technical_teams=True,
        )
        self.ts_a = User.objects.create_user(
            username='ts_a', password=password, role='technical_sales', email='ts_a@example.com', initials='TSA',
        )
        self.ts_b = User.objects.create_user(
            username='ts_b', password=password, role='technical_sales', email='ts_b@example.com', initials='TSB',
        )
        self.ts_none = User.objects.create_user(
            username='ts_none', password=password, role='technical_sales', email='ts_none@example.com', initials='TSN',
        )

        self.team_a.technical_sales.add(self.ts_a)
        self.team_b.technical_sales.add(self.ts_b)

    # --- Team scoping helpers -------------------------------------------------

    def test_handles_all_flag_returns_every_technical_team(self):
        self.assertEqual(
            technical_sales_team_ids(self.ts_solo),
            {self.team_a.id, self.team_b.id},
        )

    def test_explicit_attachment_limits_to_attached_team_only(self):
        self.assertEqual(technical_sales_team_ids(self.ts_a), {self.team_a.id})
        self.assertEqual(technical_sales_team_ids(self.ts_b), {self.team_b.id})

    def test_ts_without_team_returns_no_team_ids(self):
        self.assertEqual(technical_sales_team_ids(self.ts_none), set())

    def test_single_active_ts_without_assignment_covers_all_teams(self):
        for ts in [self.ts_solo, self.ts_a, self.ts_b]:
            ts.is_active = False
            ts.save(update_fields=['is_active'])

        self.assertEqual(
            technical_sales_team_ids(self.ts_none),
            {self.team_a.id, self.team_b.id},
        )

    # --- Customer visibility --------------------------------------------------

    def test_ts_without_team_sees_no_customers(self):
        self.assertFalse(visible_customers_queryset(self.ts_none).exists())

    def test_single_active_ts_without_assignment_sees_all_customers(self):
        for ts in [self.ts_solo, self.ts_a, self.ts_b]:
            ts.is_active = False
            ts.save(update_fields=['is_active'])

        visible = visible_customers_queryset(self.ts_none)
        self.assertTrue(visible.filter(pk=self.customer_a.pk).exists())
        self.assertTrue(visible.filter(pk=self.customer_b.pk).exists())

    def test_ts_sees_customers_of_covered_team_only(self):
        visible = visible_customers_queryset(self.ts_a)
        self.assertTrue(visible.filter(pk=self.customer_a.pk).exists())
        self.assertFalse(visible.filter(pk=self.customer_b.pk).exists())

    def test_solo_ts_sees_customers_of_both_teams(self):
        visible = visible_customers_queryset(self.ts_solo)
        self.assertTrue(visible.filter(pk=self.customer_a.pk).exists())
        self.assertTrue(visible.filter(pk=self.customer_b.pk).exists())

    def test_technical_manager_sees_their_team_customers_only(self):
        visible = visible_customers_queryset(self.techmgr_a)
        self.assertTrue(visible.filter(pk=self.customer_a.pk).exists())
        self.assertFalse(visible.filter(pk=self.customer_b.pk).exists())

    # --- Manager visibility of staff -----------------------------------------

    def test_technical_manager_staff_scope(self):
        staff_ids = set(
            technical_sales_users_for_teams(tech_manager_team_ids(self.techmgr_a))
            .values_list('id', flat=True)
        )
        self.assertIn(self.ts_a.id, staff_ids)
        self.assertIn(self.ts_solo.id, staff_ids)
        self.assertNotIn(self.ts_b.id, staff_ids)
        self.assertNotIn(self.ts_none.id, staff_ids)

    def test_technical_manager_staff_scope_includes_singleton_ts(self):
        for ts in [self.ts_solo, self.ts_a, self.ts_b]:
            ts.is_active = False
            ts.save(update_fields=['is_active'])

        staff_ids = set(
            technical_sales_users_for_teams(tech_manager_team_ids(self.techmgr_a))
            .values_list('id', flat=True)
        )
        self.assertIn(self.ts_none.id, staff_ids)

    # --- Proposal visibility --------------------------------------------------

    def test_ts_proposal_visibility_is_author_only(self):
        proposal_a = self._make_proposal(self.ts_a, self.customer_a, Decimal('100.00'))
        proposal_b = self._make_proposal(self.ts_b, self.customer_b, Decimal('100.00'))

        visible = visible_proposals_queryset(self.ts_a)
        self.assertTrue(visible.filter(pk=proposal_a.pk).exists())
        self.assertFalse(visible.filter(pk=proposal_b.pk).exists())

    # --- Approval rule --------------------------------------------------------

    def test_non_mastered_ts_always_requires_approval_regardless_of_price(self):
        proposal = self._make_proposal(self.ts_a, self.customer_a, Decimal('100.00'))
        proposal.calculate_totals()
        proposal.refresh_from_db()

        self.assertTrue(proposal.approval_required)

    def test_low_price_non_ts_still_skips_approval(self):
        # Contrast case: the price threshold must remain in force for non-TS authors.
        proposal = self._make_proposal(self.seller_a, self.customer_a, Decimal('100.00'))
        proposal.calculate_totals()
        proposal.refresh_from_db()

        self.assertFalse(proposal.approval_required)

    def test_mastered_ts_skips_approval_even_at_high_price(self):
        self.ts_a.ts_approval_exempt = True
        self.ts_a.save(update_fields=['ts_approval_exempt'])

        proposal = self._make_proposal(self.ts_a, self.customer_a, Decimal('900000.00'))
        proposal.calculate_totals()
        proposal.refresh_from_db()

        self.assertFalse(proposal.approval_required)

    def test_ts_approval_chain_targets_team_technical_manager(self):
        proposal = self._make_proposal(self.ts_a, self.customer_a, Decimal('100.00'))
        proposal.calculate_totals()

        self.assertEqual([u.id for u in proposal.get_approval_chain()], [self.techmgr_a.id])

    def test_ts_without_team_has_no_approval_chain(self):
        proposal = self._make_proposal(self.ts_none, self.customer_a, Decimal('100.00'))
        proposal.calculate_totals()

        self.assertEqual(proposal.get_approval_chain(), [])

    # --- Auto-funnel credit ---------------------------------------------------

    def test_auto_funnel_entry_credits_ts_creator(self):
        proposal = self._make_proposal(self.ts_a, self.customer_a, Decimal('500.00'))
        proposal.calculate_totals()

        update_sales_funnel(proposal)

        funnel = SalesFunnel.objects.get(proposal=proposal)
        self.assertEqual(funnel.salesperson_id, self.ts_a.id)

    # --- Helper ---------------------------------------------------------------

    def _make_proposal(self, creator, customer, unit_price):
        proposal = Proposal.objects.create(
            customer=customer,
            created_by=creator,
            subject='Technical Sales Proposal',
        )
        ProposalItem.objects.create(
            proposal=proposal,
            part_number='TS-001',
            description='Technical service',
            quantity=Decimal('1'),
            unit_cost=Decimal('10.00'),
            unit_price=unit_price,
        )
        return proposal


class QuotaManagementExecutiveAccessTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.avp_a = User.objects.create_user(
            username='quota_avp_a', password='pass', role='avp'
        )
        self.avp_b = User.objects.create_user(
            username='quota_avp_b', password='pass', role='avp'
        )
        self.supervisor = User.objects.create_user(
            username='quota_supervisor', password='pass', role='supervisor'
        )
        self.team_a = Team.objects.create(name='Quota Team A', avp=self.avp_a)
        self.team_b = Team.objects.create(name='Quota Team B', avp=self.avp_b)
        self.group_a = Group.objects.create(
            name='Quota Group A',
            team=self.team_a,
            group_type='regular',
            supervisor=self.supervisor,
        )
        Group.objects.create(
            name='Quota Group B',
            team=self.team_b,
            group_type='regular',
            supervisor=self.supervisor,
        )
        self.salesperson = User.objects.create_user(
            username='quota_salesperson', password='pass', role='salesperson'
        )
        self.membership = TeamMembership.objects.create(
            user=self.salesperson,
            group=self.group_a,
            quota=Decimal('100000.00'),
        )

    def test_gm_and_vp_can_manage_quotas_for_all_teams(self):
        for role in ('gm', 'vp'):
            with self.subTest(role=role):
                executive = User.objects.create_user(
                    username=f'quota_{role}', password='pass', role=role
                )
                self.client.force_login(executive)

                response = self.client.get(reverse('quota_management'))

                self.assertEqual(response.status_code, 200)
                team_names = [data['team'].name for data in response.context['team_data']]
                self.assertEqual(team_names, ['Quota Team A', 'Quota Team B'])
                self.assertFalse(response.context['include_personal_quota'])
                self.assertContains(response, 'Quota Management')
                self.assertContains(response, reverse('quota_management'))

    def test_gm_and_vp_can_update_salesperson_quotas(self):
        for role in ('gm', 'vp'):
            with self.subTest(role=role):
                executive = User.objects.create_user(
                    username=f'quota_editor_{role}', password='pass', role=role
                )
                self.client.force_login(executive)
                response = self.client.post(
                    reverse('update_member_quota', args=[self.membership.pk]),
                    {'quota': '150000.00'},
                )

                self.assertEqual(response.status_code, 302)
                self.membership.refresh_from_db()
                self.assertEqual(self.membership.quota, Decimal('150000.00'))

    def test_avp_quota_management_remains_limited_to_own_team(self):
        self.client.force_login(self.avp_a)

        response = self.client.get(reverse('quota_management'))

        self.assertEqual(response.status_code, 200)
        team_names = [data['team'].name for data in response.context['team_data']]
        self.assertEqual(team_names, ['Quota Team A'])
        self.assertTrue(response.context['include_personal_quota'])
        self.assertContains(response, 'My Personal Quota (AVP)')

    def test_other_roles_cannot_access_quota_management(self):
        salesperson = self.salesperson
        self.client.force_login(salesperson)

        response = self.client.get(reverse('quota_management'))

        self.assertEqual(response.status_code, 403)
