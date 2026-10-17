from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
from users.models import User
from teams.models import Team, Group, TeamMembership, SupervisorCommitment
from sales_funnel.models import SalesFunnel
from sales_monitoring.views import team_performance, get_executive_dashboard_data

class SupervisorCommitmentTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.avp = User.objects.create_user(username='avp1', password='pass', role='avp')
        self.supervisor = User.objects.create_user(username='sup1', password='pass', role='supervisor')
        self.sp1 = User.objects.create_user(username='sp1', password='pass', role='salesperson')
        self.sp2 = User.objects.create_user(username='sp2', password='pass', role='salesperson')
        self.team = Team.objects.create(name='TEAM A', avp=self.avp)
        self.group = Group.objects.create(name='Group X', team=self.team, group_type='regular', supervisor=self.supervisor)
        TeamMembership.objects.create(user=self.sp1, group=self.group, quota=Decimal('100000.00'))
        TeamMembership.objects.create(user=self.sp2, group=self.group, quota=Decimal('100000.00'))
        today = timezone.now().date()
        month_start = today.replace(day=1)
        SalesFunnel.objects.create(
            date_created=today,
            company_name='Co1',
            requirement_description='Req1',
            cost=Decimal('100000.00'),
            retail=Decimal('200000.00'),
            stage='quoted',
            salesperson=self.sp1,
            deal_outcome='won',
            closed_date=today
        )
        SalesFunnel.objects.create(
            date_created=today,
            company_name='Co2',
            requirement_description='Req2',
            cost=Decimal('50000.00'),
            retail=Decimal('120000.00'),
            stage='quoted',
            salesperson=self.sp2,
            deal_outcome='won',
            closed_date=today
        )
        SupervisorCommitment.objects.create(group=self.group, supervisor=self.supervisor, month=month_start, target_profit=Decimal('300000.00'))

    def test_avp_dashboard_shows_supervisor_commitment_progress(self):
        self.client.force_login(self.avp)
        url = reverse('sales_monitoring:dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        commitments = response.context.get('supervisor_commitments')
        self.assertTrue(commitments)
        item = next((c for c in commitments if c['group'] == self.group), None)
        self.assertIsNotNone(item)
        self.assertEqual(item['supervisor_name'], self.supervisor.get_full_name() or self.supervisor.username)
        self.assertGreater(item['actual_profit'], 0)
        self.assertEqual(Decimal(item['target_profit']), Decimal('300000.00'))

    def test_team_performance_uses_commitment_for_group_quota(self):
        self.client.force_login(self.avp)
        url = reverse('sales_monitoring:team_performance')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.context.get('performance_data')
        self.assertTrue(data)
        gdata = next((d for d in data if d['group'] == self.group), None)
        self.assertIsNotNone(gdata)
        self.assertEqual(Decimal(gdata['group_quota']), Decimal('300000.00'))


class ExecutiveDashboardRankingTests(TestCase):
    def setUp(self):
        self.avp = User.objects.create_user(username='avp_exec', password='pass', role='avp')
        self.supervisor = User.objects.create_user(username='sup_exec', password='pass', role='supervisor')
        self.team = Team.objects.create(name='TEAM EXEC', avp=self.avp)
        self.group = Group.objects.create(
            name='Group Exec',
            team=self.team,
            group_type='regular',
            supervisor=self.supervisor,
        )

        self.assigned_salesperson = User.objects.create_user(
            username='assigned_sp',
            password='pass',
            role='salesperson',
            first_name='Assigned',
            last_name='Rep',
        )
        TeamMembership.objects.create(
            user=self.assigned_salesperson,
            group=self.group,
            quota=Decimal('100000.00'),
        )

        self.unassigned_salesperson = User.objects.create_user(
            username='unassigned_sp',
            password='pass',
            role='salesperson',
            first_name='Unassigned',
            last_name='Rep',
        )
        self.inactive_salesperson = User.objects.create_user(
            username='inactive_sp',
            password='pass',
            role='salesperson',
            first_name='Inactive',
            last_name='Rep',
            is_active=False,
        )
        TeamMembership.objects.create(
            user=self.inactive_salesperson,
            group=self.group,
            quota=Decimal('100000.00'),
        )

        today = timezone.now().date()
        SalesFunnel.objects.create(
            date_created=today,
            company_name='Assigned Co',
            requirement_description='Assigned deal',
            cost=Decimal('100000.00'),
            retail=Decimal('300000.00'),
            stage='quoted',
            salesperson=self.assigned_salesperson,
            deal_outcome='won',
            closed_date=today,
        )
        SalesFunnel.objects.create(
            date_created=today,
            company_name='Unassigned Co',
            requirement_description='Unassigned deal',
            cost=Decimal('100000.00'),
            retail=Decimal('900000.00'),
            stage='quoted',
            salesperson=self.unassigned_salesperson,
            deal_outcome='won',
            closed_date=today,
        )
        SalesFunnel.objects.create(
            date_created=today,
            company_name='Inactive Co',
            requirement_description='Inactive deal',
            cost=Decimal('100000.00'),
            retail=Decimal('800000.00'),
            stage='quoted',
            salesperson=self.inactive_salesperson,
            deal_outcome='won',
            closed_date=today,
        )

    def test_individual_rankings_exclude_unassigned_and_inactive_salespeople(self):
        data = get_executive_dashboard_data()

        usernames = [item['salesperson'].username for item in data['individual_performance']]

        self.assertIn(self.assigned_salesperson.username, usernames)
        self.assertNotIn(self.unassigned_salesperson.username, usernames)
        self.assertNotIn(self.inactive_salesperson.username, usernames)
