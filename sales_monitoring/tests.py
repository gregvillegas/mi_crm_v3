from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from users.models import User
from teams.models import Team, Group, TeamMembership, RoleMonthlyQuota, CompanyAnnualTarget
from sales_funnel.models import SalesFunnel
from sales_monitoring.views import team_performance, get_executive_dashboard_data
from sales_monitoring.models import ActivityType, SalesActivity
from sales_monitoring.fiscal import fiscal_year_for_date

class SupervisorGroupQuotaTests(TestCase):
    """Group monthly targets derive from rep quotas plus the supervisor's RoleMonthlyQuota.

    SupervisorCommitment is a legacy monthly model that no dashboard reads; the AVP
    dashboard and Team Performance build group targets from TeamMembership.quota plus
    the supervisor's RoleMonthlyQuota (falling back to RoleMonthlyQuota.DEFAULT_AMOUNT
    when no explicit quota is set for the month).
    """

    def setUp(self):
        self.client = Client()
        self.avp = User.objects.create_user(username='avp1', password='pass', role='avp')
        self.supervisor = User.objects.create_user(
            username='sup1', password='pass', role='supervisor',
            first_name='Sup', last_name='One',
        )
        self.sp1 = User.objects.create_user(username='sp1', password='pass', role='salesperson')
        self.sp2 = User.objects.create_user(username='sp2', password='pass', role='salesperson')
        self.team = Team.objects.create(name='TEAM A', avp=self.avp)
        self.group = Group.objects.create(name='Group X', team=self.team, group_type='regular', supervisor=self.supervisor)
        TeamMembership.objects.create(user=self.sp1, group=self.group, quota=Decimal('100000.00'))
        TeamMembership.objects.create(user=self.sp2, group=self.group, quota=Decimal('100000.00'))
        today = timezone.now().date()
        self.month_start = today.replace(day=1)
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

    def test_avp_dashboard_uses_role_monthly_quota_for_group_target(self):
        self.client.force_login(self.avp)
        response = self.client.get(reverse('sales_monitoring:dashboard'))

        self.assertEqual(response.status_code, 200)
        achievements = response.context.get('group_achievements')
        self.assertTrue(achievements)
        item = next((a for a in achievements if a['group'] == self.group), None)
        self.assertIsNotNone(item)
        self.assertEqual(item['supervisor_name'], self.supervisor.get_full_name())
        self.assertGreater(item['actual_profit'], 0)
        # 100k + 100k rep quotas + supervisor default quota (200k)
        self.assertEqual(Decimal(item['total_quota']), Decimal('400000.00'))

    def test_team_performance_uses_role_monthly_quota_for_group_quota(self):
        RoleMonthlyQuota.objects.create(
            user=self.supervisor, month=self.month_start, amount=Decimal('250000.00'),
        )
        self.client.force_login(self.avp)
        response = self.client.get(reverse('sales_monitoring:team_performance'))

        self.assertEqual(response.status_code, 200)
        data = response.context.get('performance_data')
        self.assertTrue(data)
        gdata = next((d for d in data if d['group'] == self.group), None)
        self.assertIsNotNone(gdata)
        # 100k + 100k rep quotas + 250k supervisor RoleMonthlyQuota
        self.assertEqual(Decimal(gdata['group_quota']), Decimal('450000.00'))


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


class ActivityCalendarAccessTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.avp_a = User.objects.create_user(
            username='calendar_avp_a', password='pass', role='avp'
        )
        self.avp_b = User.objects.create_user(
            username='calendar_avp_b', password='pass', role='avp'
        )
        self.supervisor = User.objects.create_user(
            username='calendar_supervisor', password='pass', role='supervisor'
        )
        self.team_a = Team.objects.create(name='Calendar Team A', avp=self.avp_a)
        self.team_b = Team.objects.create(name='Calendar Team B', avp=self.avp_b)
        self.group_a = Group.objects.create(
            name='Calendar Group A',
            team=self.team_a,
            group_type='regular',
            supervisor=self.supervisor,
        )
        self.group_b = Group.objects.create(
            name='Calendar Group B',
            team=self.team_b,
            group_type='regular',
            supervisor=self.supervisor,
        )
        self.salesperson_a = User.objects.create_user(
            username='calendar_sp_a',
            password='pass',
            role='salesperson',
            first_name='Ava',
            last_name='Rep',
        )
        self.salesperson_b = User.objects.create_user(
            username='calendar_sp_b',
            password='pass',
            role='salesperson',
            first_name='Ben',
            last_name='Rep',
        )
        TeamMembership.objects.create(user=self.salesperson_a, group=self.group_a)
        TeamMembership.objects.create(user=self.salesperson_b, group=self.group_b)

        self.activity_type = ActivityType.objects.create(name='Calendar Meeting')
        self.activity_a = self._create_activity(
            self.activity_type, self.salesperson_a, 'Activity Team A'
        )
        self.activity_b = self._create_activity(
            self.activity_type, self.salesperson_b, 'Activity Team B'
        )

    @staticmethod
    def _create_activity(activity_type, salesperson, title):
        start = timezone.now() + timedelta(days=1)
        return SalesActivity.objects.create(
            title=title,
            activity_type=activity_type,
            salesperson=salesperson,
            scheduled_start=start,
            scheduled_end=start + timedelta(hours=1),
        )

    def _get_events(self, user):
        self.client.force_login(user)
        start = timezone.now() - timedelta(days=1)
        end = timezone.now() + timedelta(days=5)
        return self.client.get(
            reverse('sales_monitoring:activity_calendar_events'),
            {'start': start.isoformat(), 'end': end.isoformat()},
        )

    def test_admin_gm_and_vp_see_all_teams(self):
        for role in ('admin', 'gm', 'vp'):
            with self.subTest(role=role):
                user = User.objects.create_user(
                    username=f'calendar_{role}', password='pass', role=role
                )
                response = self._get_events(user)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    {event['title'] for event in response.json()},
                    {'Activity Team A', 'Activity Team B'},
                )

    def test_avp_only_sees_activities_in_managed_teams(self):
        response = self._get_events(self.avp_a)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [event['title'] for event in response.json()],
            ['Activity Team A'],
        )
        self.assertEqual(response.json()[0]['extendedProps']['team'], self.team_a.name)

    def test_salesperson_only_sees_own_activities(self):
        response = self._get_events(self.salesperson_a)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [event['title'] for event in response.json()],
            ['Activity Team A'],
        )

    def test_marketing_cannot_access_activity_calendar(self):
        marketing = User.objects.create_user(
            username='calendar_marketing', password='pass', role='marketing'
        )
        self.client.force_login(marketing)

        page_response = self.client.get(
            reverse('sales_monitoring:activity_calendar')
        )
        events_response = self.client.get(
            reverse('sales_monitoring:activity_calendar_events'),
            {
                'start': timezone.now().isoformat(),
                'end': (timezone.now() + timedelta(days=1)).isoformat(),
            },
        )

        self.assertEqual(page_response.status_code, 403)
        self.assertEqual(events_response.status_code, 403)

    def test_calendar_supports_month_week_and_day_initial_views(self):
        self.client.force_login(
            User.objects.create_user(
                username='calendar_admin', password='pass', role='admin'
            )
        )
        url = reverse('sales_monitoring:activity_calendar')
        selected_date = timezone.localdate().isoformat()

        expected_views = {
            'month': 'dayGridMonth',
            'week': 'timeGridWeek',
            'day': 'timeGridDay',
        }
        for mode, expected_view in expected_views.items():
            with self.subTest(mode=mode):
                response = self.client.get(
                    url,
                    {'view': mode, 'date': selected_date},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['initial_view'], expected_view)
                self.assertContains(response, 'dayGridMonth,timeGridWeek,timeGridDay')

    def test_executive_dashboard_links_to_calendar(self):
        gm = User.objects.create_user(
            username='calendar_dashboard_gm', password='pass', role='gm'
        )
        self.client.force_login(gm)

        response = self.client.get(reverse('sales_monitoring:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('sales_monitoring:activity_calendar'))
        self.assertContains(response, reverse('sales_monitoring:all_activities'))

    def test_all_activities_page_sorts_by_activity_type(self):
        first_type = ActivityType.objects.create(name='A Client Call')
        self._create_activity(
            first_type, self.salesperson_b, 'Activity sorted first'
        )
        admin = User.objects.create_user(
            username='activity_list_admin', password='pass', role='admin'
        )
        self.client.force_login(admin)

        response = self.client.get(reverse('sales_monitoring:all_activities'))

        self.assertEqual(response.status_code, 200)
        names = [activity.activity_type.name for activity in response.context['activities']]
        self.assertEqual(
            names,
            ['A Client Call', 'Calendar Meeting', 'Calendar Meeting'],
        )
        self.assertContains(response, 'sorted by activity type')

    def test_non_executive_cannot_open_all_activities_page(self):
        self.client.force_login(self.salesperson_a)

        response = self.client.get(reverse('sales_monitoring:all_activities'))

        self.assertEqual(response.status_code, 403)

    def test_all_activity_filters_can_be_combined(self):
        first_type = ActivityType.objects.create(name='A Client Call')
        self._create_activity(
            first_type, self.salesperson_b, 'Other activity type'
        )
        admin = User.objects.create_user(
            username='activity_filter_admin', password='pass', role='admin'
        )
        self.client.force_login(admin)

        response = self.client.get(
            reverse('sales_monitoring:all_activities'),
            {
                'activity_type': self.activity_type.pk,
                'team': self.team_a.pk,
                'group': self.group_a.pk,
                'salesperson_id': self.salesperson_a.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [activity.title for activity in response.context['activities']],
            ['Activity Team A'],
        )
        self.assertEqual(response.context['selected_team'], self.team_a.pk)
        self.assertEqual(response.context['selected_group'], self.group_a.pk)

        type_response = self.client.get(
            reverse('sales_monitoring:all_activities'),
            {'activity_type': first_type.pk},
        )
        self.assertEqual(
            [activity.title for activity in type_response.context['activities']],
            ['Other activity type'],
        )

    def test_salesperson_autocomplete_returns_team_scoped_matches(self):
        admin = User.objects.create_user(
            username='activity_search_admin', password='pass', role='admin'
        )
        self.client.force_login(admin)

        response = self.client.get(
            reverse('sales_monitoring:all_activities_salesperson_suggestions'),
            {
                'q': 'Ava',
                'team': self.team_a.pk,
                'group': self.group_a.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item['id'] for item in response.json()['results']],
            [self.salesperson_a.pk],
        )
        self.assertEqual(
            response.json()['results'][0]['label'],
            'Ava Rep (calendar_sp_a)',
        )

        outside_team_response = self.client.get(
            reverse('sales_monitoring:all_activities_salesperson_suggestions'),
            {'q': 'Ava', 'team': self.team_b.pk},
        )
        self.assertEqual(outside_team_response.json()['results'], [])

    def test_non_executive_cannot_search_salespeople_for_global_filters(self):
        self.client.force_login(self.salesperson_a)

        response = self.client.get(
            reverse('sales_monitoring:all_activities_salesperson_suggestions'),
            {'q': 'Ava'},
        )

        self.assertEqual(response.status_code, 403)


class PipelineIntelligenceTests(TestCase):
    """Phase 0 read-only pipeline analytics (sales_monitoring.analytics)."""

    def setUp(self):
        self.client = Client()
        self.today = timezone.now().date()

        self.admin = User.objects.create_user(username='pi_admin', password='pass', role='admin')
        self.avp = User.objects.create_user(username='pi_avp', password='pass', role='avp')
        self.supervisor = User.objects.create_user(username='pi_sup', password='pass', role='supervisor')
        self.sp1 = User.objects.create_user(
            username='pi_sp1', password='pass', role='salesperson',
            first_name='Pi', last_name='One',
        )
        self.team = Team.objects.create(name='PI TEAM', avp=self.avp)
        self.group = Group.objects.create(
            name='PI Group', team=self.team, group_type='regular', supervisor=self.supervisor,
        )
        TeamMembership.objects.create(user=self.sp1, group=self.group, quota=Decimal('200000.00'))

        # A separate team/rep that must stay out of the AVP's scope.
        self.other_avp = User.objects.create_user(username='pi_avp2', password='pass', role='avp')
        self.other_supervisor = User.objects.create_user(username='pi_sup2', password='pass', role='supervisor')
        self.other_sp = User.objects.create_user(username='pi_sp_other', password='pass', role='salesperson')
        self.other_team = Team.objects.create(name='PI OTHER TEAM', avp=self.other_avp)
        self.other_group = Group.objects.create(
            name='PI Other Group', team=self.other_team, group_type='regular',
            supervisor=self.other_supervisor,
        )
        TeamMembership.objects.create(user=self.other_sp, group=self.other_group, quota=Decimal('200000.00'))

        # Overdue, high-value active deal owned by sp1.
        SalesFunnel.objects.create(
            date_created=self.today,
            company_name='Stalled Co',
            requirement_description='Overdue requirement',
            cost=Decimal('300000.00'),
            retail=Decimal('600000.00'),
            stage='quoted',
            salesperson=self.sp1,
            expected_close_date=self.today - timedelta(days=10),
        )
        # Active deal that is not yet due.
        SalesFunnel.objects.create(
            date_created=self.today,
            company_name='Healthy Co',
            requirement_description='Future requirement',
            cost=Decimal('50000.00'),
            retail=Decimal('100000.00'),
            stage='quoted',
            salesperson=self.sp1,
            expected_close_date=self.today + timedelta(days=10),
        )
        # Won deal in the period (feeds performer/velocity).
        SalesFunnel.objects.create(
            date_created=self.today - timedelta(days=20),
            company_name='Won Co',
            requirement_description='Won requirement',
            cost=Decimal('120000.00'),
            retail=Decimal('200000.00'),
            stage='quoted',
            salesperson=self.sp1,
            deal_outcome='won',
            is_closed=True,
            closed_date=self.today,
        )
        # Overdue active deal owned by an out-of-scope rep.
        SalesFunnel.objects.create(
            date_created=self.today,
            company_name='Other Co',
            requirement_description='Other requirement',
            cost=Decimal('900000.00'),
            retail=Decimal('900000.00'),
            stage='quoted',
            salesperson=self.other_sp,
            expected_close_date=self.today - timedelta(days=30),
        )

    def test_executive_can_open_pipeline_intelligence(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('sales_monitoring:pipeline_intelligence'))

        self.assertEqual(response.status_code, 200)
        for key in ('period', 'coverage', 'stalled', 'performers',
                    'lead_quality', 'hygiene', 'velocity', 'discounting'):
            self.assertIn(key, response.context)
        # The page is reachable from the Monitoring menu.
        self.assertContains(response, reverse('sales_monitoring:pipeline_intelligence'))

    def test_non_executive_cannot_open_pipeline_intelligence(self):
        self.client.force_login(self.sp1)
        response = self.client.get(reverse('sales_monitoring:pipeline_intelligence'))
        self.assertEqual(response.status_code, 403)

    def test_stalled_deals_flag_only_overdue_active_deals(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('sales_monitoring:pipeline_intelligence'))

        stalled = response.context['stalled']
        companies = [row['company'] for row in stalled['rows']]
        self.assertIn('Stalled Co', companies)
        self.assertIn('Other Co', companies)
        self.assertNotIn('Healthy Co', companies)
        self.assertNotIn('Won Co', companies)

        row = next(r for r in stalled['rows'] if r['company'] == 'Stalled Co')
        self.assertEqual(row['days_overdue'], 10)
        self.assertTrue(row['high_value'])

    def test_stalled_drilldown_paginates_and_filters_by_value(self):
        self.client.force_login(self.admin)
        url = reverse('sales_monitoring:pipeline_intelligence_stalled_deals')

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total'], 2)

        # Both 600k and 900k clear the 500k bar.
        filtered = self.client.get(url, {'min_value': '500000'})
        self.assertEqual(filtered.context['total'], 2)

        # Nothing clears 1M.
        high = self.client.get(url, {'min_value': '1000000'})
        self.assertEqual(high.context['total'], 0)

    def test_coverage_uses_company_annual_target(self):
        fy = fiscal_year_for_date(self.today)
        CompanyAnnualTarget.objects.create(year=fy, amount=Decimal('4000000.00'))

        self.client.force_login(self.admin)
        response = self.client.get(reverse('sales_monitoring:pipeline_intelligence'))

        coverage = response.context['coverage']
        self.assertEqual(coverage['targets']['annual'], Decimal('4000000.00'))
        self.assertEqual(coverage['targets']['source'], 'Company annual target')
        # Open pipeline = 600k + 100k + 900k (won deal excluded).
        self.assertEqual(coverage['pipeline'], Decimal('1600000.00'))

    def test_avp_scope_excludes_other_teams(self):
        self.client.force_login(self.avp)
        response = self.client.get(reverse('sales_monitoring:pipeline_intelligence'))

        self.assertEqual(response.status_code, 200)
        coverage = response.context['coverage']
        # AVP sees only their own team's pipeline: 600k + 100k.
        self.assertEqual(coverage['pipeline'], Decimal('700000.00'))
        companies = [row['company'] for row in response.context['stalled']['rows']]
        self.assertIn('Stalled Co', companies)
        self.assertNotIn('Other Co', companies)
