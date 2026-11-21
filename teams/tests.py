from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from customers.models import Customer
from customers.permissions import visible_customers_queryset
from sales_funnel.models import SalesFunnel
from sales_proposals.models import Proposal, ProposalItem
from sales_proposals.views import update_sales_funnel, visible_proposals_queryset
from teams.forms import GroupEditForm
from teams.models import (
    Group,
    RoleMonthlyQuota,
    Team,
    TeamMembership,
    TeamMembershipQuotaLog,
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
                edit_response = self.client.get(
                    reverse('update_member_quota', args=[self.membership.pk])
                )
                self.assertEqual(edit_response.status_code, 200)
                self.assertContains(edit_response, 'Save Quota')
                self.assertContains(edit_response, 'Cancel')
                self.assertContains(edit_response, 'Back to Quota Management')
                self.assertIn(
                    'quota-amount-input',
                    edit_response.context['form'].fields['quota'].widget.attrs['class'],
                )
                self.assertContains(edit_response, 'max-width: 360px')

                response = self.client.post(
                    reverse('update_member_quota', args=[self.membership.pk]),
                    {'quota': '150000.00'},
                )

                self.assertRedirects(response, reverse('quota_management'))
                self.membership.refresh_from_db()
                self.assertEqual(self.membership.quota, Decimal('150000.00'))

    def test_role_quota_edit_saves_and_returns_to_quota_management(self):
        quota_url = reverse('update_role_quota', args=[self.supervisor.pk])
        for role in ('gm', 'vp'):
            with self.subTest(role=role):
                executive = User.objects.create_user(
                    username=f'role_quota_editor_{role}',
                    password='pass',
                    role=role,
                )
                self.client.force_login(executive)

                edit_response = self.client.get(quota_url)
                self.assertEqual(edit_response.status_code, 200)
                self.assertContains(edit_response, 'Save Quota')
                self.assertContains(edit_response, 'Back to Quota Management')
                self.assertIn(
                    'quota-amount-input',
                    edit_response.context['form'].fields['amount'].widget.attrs['class'],
                )
                self.assertContains(edit_response, 'max-width: 360px')

                response = self.client.post(
                    quota_url,
                    {'amount': '175000.00', 'notes': 'Monthly quota update'},
                )

                self.assertRedirects(response, reverse('quota_management'))
                quota = RoleMonthlyQuota.objects.get(
                    user=self.supervisor,
                    month=timezone.now().date().replace(day=1),
                )
                self.assertEqual(quota.amount, Decimal('175000.00'))
                self.assertEqual(quota.notes, 'Monthly quota update')

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


class TeamMembershipQuotaLogTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.supervisor = User.objects.create_user(
            username='log_supervisor', password='pass', role='supervisor'
        )
        self.team = Team.objects.create(name='Log Team', avp=self.supervisor)
        self.group = Group.objects.create(
            name='Log Group',
            team=self.team,
            group_type='regular',
            supervisor=self.supervisor,
        )
        self.salesperson = User.objects.create_user(
            username='log_salesperson', password='pass', role='salesperson'
        )
        self.membership = TeamMembership.objects.create(
            user=self.salesperson,
            group=self.group,
            quota=Decimal('100000.00'),
        )
        self.editor = User.objects.create_user(
            username='log_editor_gm', password='pass', role='gm'
        )

    def _post(self, quota_value):
        return self.client.post(
            reverse('update_member_quota', args=[self.membership.pk]),
            {'quota': quota_value},
        )

    def test_increase_is_logged(self):
        self.client.force_login(self.editor)

        response = self._post('150000.00')

        self.assertRedirects(response, reverse('quota_management'))
        log = TeamMembershipQuotaLog.objects.get(team_membership=self.membership)
        self.assertEqual(log.previous_quota, Decimal('100000.00'))
        self.assertEqual(log.new_quota, Decimal('150000.00'))
        self.assertEqual(log.change_type, 'increase')
        self.assertEqual(log.changed_by, self.editor)

    def test_decrease_is_logged(self):
        self.client.force_login(self.editor)

        self._post('75000.00')

        log = TeamMembershipQuotaLog.objects.get(team_membership=self.membership)
        self.assertEqual(log.change_type, 'decrease')
        self.assertEqual(log.new_quota, Decimal('75000.00'))

    def test_no_change_is_logged_as_no_change(self):
        self.client.force_login(self.editor)

        self._post('100000.00')

        log = TeamMembershipQuotaLog.objects.get(team_membership=self.membership)
        self.assertEqual(log.change_type, 'no_change')
        self.assertEqual(log.previous_quota, log.new_quota)

    def test_multiple_changes_create_multiple_logs(self):
        self.client.force_login(self.editor)

        self._post('200000.00')
        self._post('50000.00')

        logs = list(TeamMembershipQuotaLog.objects.filter(
            team_membership=self.membership
        ).order_by('-changed_at'))
        self.assertEqual(len(logs), 2)
        # Most recent is the decrease to 50k
        self.assertEqual(logs[0].change_type, 'decrease')
        self.assertEqual(logs[0].previous_quota, Decimal('200000.00'))
        self.assertEqual(logs[0].new_quota, Decimal('50000.00'))
        # First was the increase to 200k
        self.assertEqual(logs[1].change_type, 'increase')

    def test_history_displayed_on_update_page(self):
        TeamMembershipQuotaLog.objects.create(
            team_membership=self.membership,
            previous_quota=Decimal('100000.00'),
            new_quota=Decimal('120000.00'),
            change_type='increase',
            changed_by=self.editor,
        )
        self.client.force_login(self.editor)

        response = self.client.get(
            reverse('update_member_quota', args=[self.membership.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Quota Change History')
        self.assertContains(response, 'Increase')
        self.assertContains(response, '100,000.00')
        self.assertContains(response, '120,000.00')


class GroupEditFormMembershipTests(TestCase):
    """Verify that group membership is role-segregated by group type:
    regular groups list salespeople, TSG groups list technical_sales users."""

    def setUp(self):
        self.techmgr = User.objects.create_user(
            username='tmgr_membership', password='pass', role='techmgr'
        )
        self.supervisor = User.objects.create_user(
            username='sup_membership', password='pass', role='supervisor'
        )
        self.team = Team.objects.create(
            name='TSG Team', tech_manager=self.techmgr,
        )
        self.regular_group = Group.objects.create(
            name='Regular Group', team=self.team, group_type='regular',
            supervisor=self.supervisor,
        )
        self.tsg_group = Group.objects.create(
            name='TSG A', team=self.team, group_type='tsg',
        )
        self.salesperson = User.objects.create_user(
            username='sp_member', password='pass', role='salesperson',
            first_name='Sales', last_name='Person',
        )
        self.tech_sales = User.objects.create_user(
            username='ts_member', password='pass', role='technical_sales',
            first_name='Tech', last_name='Sales',
        )

    def test_regular_group_offers_salespeople_only(self):
        form = GroupEditForm(instance=self.regular_group)
        member_ids = set(form.fields['members'].queryset.values_list('pk', flat=True))

        self.assertIn(self.salesperson.pk, member_ids)
        self.assertNotIn(self.tech_sales.pk, member_ids)

    def test_tsg_group_offers_technical_sales_only(self):
        form = GroupEditForm(instance=self.tsg_group)
        member_ids = set(form.fields['members'].queryset.values_list('pk', flat=True))

        self.assertIn(self.tech_sales.pk, member_ids)
        self.assertNotIn(self.salesperson.pk, member_ids)

    def test_tsg_group_can_save_technical_sales_member(self):
        form = GroupEditForm(
            {
                'name': self.tsg_group.name,
                'team': self.team.pk,
                'members': [self.tech_sales.pk],
            },
            instance=self.tsg_group,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        membership = TeamMembership.objects.get(user=self.tech_sales)
        self.assertEqual(membership.group, self.tsg_group)

    def test_regular_group_cannot_add_technical_sales_member(self):
        # The form queryset excludes technical_sales, so passing one must fail
        # validation rather than silently creating a cross-role membership.
        form = GroupEditForm(
            {
                'name': self.regular_group.name,
                'team': self.team.pk,
                'members': [self.tech_sales.pk],
            },
            instance=self.regular_group,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('members', form.errors)
        self.assertFalse(
            TeamMembership.objects.filter(user=self.tech_sales).exists()
        )

    def test_current_tsg_member_remains_selectable(self):
        TeamMembership.objects.create(user=self.tech_sales, group=self.tsg_group)

        form = GroupEditForm(instance=self.tsg_group)
        member_ids = set(form.fields['members'].queryset.values_list('pk', flat=True))

        self.assertIn(self.tech_sales.pk, member_ids)
        self.assertEqual(
            set(form.fields['members'].initial), {self.tech_sales.pk}
        )


class QuotaManagementPageMembershipTests(TestCase):
    """Technical Sales members of TSG groups must appear on the Quota
    Management page so they can be assigned a quota."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='qmgmt_admin', password='pass', role='admin'
        )
        self.techmgr = User.objects.create_user(
            username='qmgmt_tm', password='pass', role='techmgr'
        )
        self.team = Team.objects.create(name='QMGMT TSG', tech_manager=self.techmgr)
        self.tsg_group = Group.objects.create(
            name='QMGMT TSG A', team=self.team, group_type='tsg',
        )
        self.tech_sales = User.objects.create_user(
            username='qmgmt_ts', password='pass', role='technical_sales',
            first_name='TS', last_name='Rep',
        )
        TeamMembership.objects.create(
            user=self.tech_sales, group=self.tsg_group, quota=Decimal('150000.00'),
        )

    def test_tsg_member_appears_on_quota_management_page(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse('quota_management'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TS Rep')
        self.assertContains(response, '150,000.00')
        self.assertContains(response, 'Technical Sales Quotas')


class TechnicalSalesTSGGroupCoverageTests(TestCase):
    """A Technical Sales user added as a member of a TSG group must cover that
    group's team's customers without also being ticked on the Team edit form."""

    def setUp(self):
        password = 'testpass123'
        self.avp = User.objects.create_user(
            username='tsgcov_avp', password=password, role='avp',
        )
        self.techmgr_a = User.objects.create_user(
            username='tsgcov_tm_a', password=password, role='techmgr',
        )
        self.techmgr_b = User.objects.create_user(
            username='tsgcov_tm_b', password=password, role='techmgr',
        )
        self.supervisor_a = User.objects.create_user(
            username='tsgcov_sup_a', password=password, role='supervisor',
        )
        self.supervisor_b = User.objects.create_user(
            username='tsgcov_sup_b', password=password, role='supervisor',
        )

        self.team_a = Team.objects.create(
            name='TSG Cov Team A', avp=self.avp, tech_manager=self.techmgr_a,
        )
        self.team_b = Team.objects.create(
            name='TSG Cov Team B', avp=self.avp, tech_manager=self.techmgr_b,
        )
        self.group_a = Group.objects.create(
            name='TSG Cov Group A', team=self.team_a, supervisor=self.supervisor_a,
        )
        self.group_b = Group.objects.create(
            name='TSG Cov Group B', team=self.team_b, supervisor=self.supervisor_b,
        )
        self.tsg_a = Group.objects.create(
            name='TSG Cov A', team=self.team_a, group_type='tsg',
        )
        self.tsg_b = Group.objects.create(
            name='TSG Cov B', team=self.team_b, group_type='tsg',
        )

        self.seller_a = User.objects.create_user(
            username='tsgcov_seller_a', password=password, role='salesperson',
        )
        self.seller_b = User.objects.create_user(
            username='tsgcov_seller_b', password=password, role='salesperson',
        )
        TeamMembership.objects.create(user=self.seller_a, group=self.group_a)
        TeamMembership.objects.create(user=self.seller_b, group=self.group_b)

        self.customer_a = Customer.objects.create(
            company_name='TSG Cov Customer A', contact_person_name='Al',
            email='al@tsgcov.test', salesperson=self.seller_a,
        )
        self.customer_b = Customer.objects.create(
            company_name='TSG Cov Customer B', contact_person_name='Bea',
            email='bea@tsgcov.test', salesperson=self.seller_b,
        )

        # Two active Technical Sales users so the singleton rule does not fire
        # and coverage must come from the TSG membership.
        self.ts_a = User.objects.create_user(
            username='tsgcov_ts_a', password=password, role='technical_sales',
        )
        self.ts_b = User.objects.create_user(
            username='tsgcov_ts_b', password=password, role='technical_sales',
        )
        self.ts_unassigned = User.objects.create_user(
            username='tsgcov_ts_none', password=password, role='technical_sales',
        )

        TeamMembership.objects.create(user=self.ts_a, group=self.tsg_a)
        TeamMembership.objects.create(user=self.ts_b, group=self.tsg_b)

    def test_tsg_membership_grants_the_group_team(self):
        self.assertEqual(technical_sales_team_ids(self.ts_a), {self.team_a.id})
        self.assertEqual(technical_sales_team_ids(self.ts_b), {self.team_b.id})

    def test_ts_without_tsg_membership_has_no_team(self):
        self.assertEqual(technical_sales_team_ids(self.ts_unassigned), set())

    def test_tsg_member_sees_their_team_customers_only(self):
        visible = visible_customers_queryset(self.ts_a)
        self.assertTrue(visible.filter(pk=self.customer_a.pk).exists())
        self.assertFalse(visible.filter(pk=self.customer_b.pk).exists())

    def test_ts_without_tsg_membership_sees_no_customers(self):
        self.assertFalse(visible_customers_queryset(self.ts_unassigned).exists())

    def test_technical_manager_sees_tsg_member_staff(self):
        staff_ids = set(
            technical_sales_users_for_teams(tech_manager_team_ids(self.techmgr_a))
            .values_list('id', flat=True)
        )
        self.assertIn(self.ts_a.id, staff_ids)
        self.assertNotIn(self.ts_b.id, staff_ids)

    def test_team_form_m2m_still_grants_coverage(self):
        # The documented Team.technical_sales path must keep working alongside
        # the new TSG-membership path.
        self.team_b.technical_sales.add(self.ts_unassigned)
        self.assertEqual(
            technical_sales_team_ids(self.ts_unassigned), {self.team_b.id}
        )

    def test_covered_team_redirects_coverage_when_tsg_has_own_team(self):
        # Mirror the real setup: TSG groups live under a dedicated "TSG" team
        # and declare which sales team they cover via Group.covered_team.
        tsg_org_team = Team.objects.create(
            name='TSG Org Team', avp=self.avp, tech_manager=self.techmgr_a,
        )
        tsg_a_in_org = Group.objects.create(
            name='TSG A in Org Team', team=tsg_org_team, group_type='tsg',
            covered_team=self.team_a,
        )
        # Use a fresh Technical Sales user (ts_a already has a membership).
        ts_covered = User.objects.create_user(
            username='tsgcov_ts_covered', password='testpass123', role='technical_sales',
        )
        TeamMembership.objects.create(user=ts_covered, group=tsg_a_in_org)

        # ts_covered now belongs to the TSG org team group but must cover team_a.
        self.assertEqual(technical_sales_team_ids(ts_covered), {self.team_a.id})
        visible = visible_customers_queryset(ts_covered)
        self.assertTrue(visible.filter(pk=self.customer_a.pk).exists())
        self.assertFalse(visible.filter(pk=self.customer_b.pk).exists())
