from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from users.models import User
from teams.models import Team, Group, TeamMembership, SupervisorCommitment
from sales_funnel.models import SalesFunnel
from sales_monitoring.views import team_performance, get_executive_dashboard_data
from sales_monitoring.models import ActivityType, SalesActivity

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
