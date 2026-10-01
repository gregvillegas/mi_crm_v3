"""
End-to-end tests for the mobile REST API.

Covers the endpoints added for the mobile clients and, importantly, the role
scoping — the API previously enforced different (and in places weaker) rules
than the web app, so these lock the agreed behaviour down.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from customers.models import Customer, CustomerCreateRequest
from sales_funnel.models import SalesFunnel
from sales_monitoring.models import ActivityType, SalesActivity
from sales_proposals.models import Proposal, ProposalApprovalStep
from teams.models import Group, Team, TeamMembership

User = get_user_model()


def make_user(username, role, **extra):
    return User.objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password='Testpass!2345',
        role=role,
        **extra,
    )


class ApiTestBase(TestCase):
    """
    Two teams, so cross-team leakage is visible.

        team_a: group_a  supervisor=sup_a   members: sales_a
        team_b: group_b  supervisor=sup_b   members: sales_b
    """

    def setUp(self):
        self.admin = make_user('admin1', 'admin')
        self.avp_a = make_user('avp_a', 'avp')
        self.avp_b = make_user('avp_b', 'avp')
        self.sup_a = make_user('sup_a', 'supervisor')
        self.sup_b = make_user('sup_b', 'supervisor')
        self.sales_a = make_user('sales_a', 'salesperson')
        self.sales_b = make_user('sales_b', 'salesperson')
        self.sm_a = make_user('sm_a', 'sm')

        self.team_a = Team.objects.create(name='Team A', avp=self.avp_a)
        self.team_b = Team.objects.create(name='Team B', avp=self.avp_b)
        self.group_a = Group.objects.create(name='Group A', team=self.team_a, supervisor=self.sup_a)
        self.group_b = Group.objects.create(name='Group B', team=self.team_b, supervisor=self.sup_b)
        self.group_a.sm_managers.add(self.sm_a)

        TeamMembership.objects.create(user=self.sales_a, group=self.group_a)
        TeamMembership.objects.create(user=self.sales_b, group=self.group_b)

        self.cust_a = Customer.objects.create(
            company_name='Alpha Corp', contact_person_name='Ann A',
            email='ann@alpha.test', salesperson=self.sales_a,
        )
        self.cust_b = Customer.objects.create(
            company_name='Beta Corp', contact_person_name='Ben B',
            email='ben@beta.test', salesperson=self.sales_b,
        )

        self.activity_type = ActivityType.objects.create(
            name='Call', icon='fas fa-phone', color='primary', requires_customer=True
        )

    def client_for(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        return client


class CustomerEndpointTests(ApiTestBase):

    def test_mine_endpoint_exists_and_returns_only_own_customers(self):
        """Regression: the Android app called this route and got a 404."""
        response = self.client_for(self.sales_a).get('/api/v1/customers/mine/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([c['company_name'] for c in response.json()], ['Alpha Corp'])

    def test_mine_is_not_swallowed_by_the_detail_route(self):
        response = self.client_for(self.sales_a).get('/api/v1/customers/mine/')
        self.assertNotEqual(response.status_code, 404)

    def test_search_filters_results(self):
        response = self.client_for(self.admin).get('/api/v1/customers/?search=Alpha')
        self.assertEqual([c['company_name'] for c in response.json()], ['Alpha Corp'])

    def test_choices_endpoint_returns_picklists(self):
        response = self.client_for(self.sales_a).get('/api/v1/customers/choices/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('industries', response.json())
        self.assertIn('territories', response.json())

    def test_list_is_unpaginated_by_default_for_legacy_clients(self):
        response = self.client_for(self.admin).get('/api/v1/customers/')
        self.assertIsInstance(response.json(), list)

    def test_pagination_is_opt_in(self):
        response = self.client_for(self.admin).get('/api/v1/customers/?page=1')
        body = response.json()
        self.assertIn('results', body)
        self.assertIn('count', body)


class ScopingTests(ApiTestBase):
    """The API must not be more permissive than the web app."""

    def test_avp_does_not_see_other_teams_customers(self):
        names = {c['company_name'] for c in self.client_for(self.avp_a).get('/api/v1/customers/').json()}
        self.assertIn('Alpha Corp', names)
        self.assertNotIn('Beta Corp', names, 'AVP could read another team\'s customers')

    def test_sm_sees_their_assigned_group(self):
        """SM used to fall through to an empty queryset, so mobile showed nothing."""
        names = {c['company_name'] for c in self.client_for(self.sm_a).get('/api/v1/customers/').json()}
        self.assertEqual(names, {'Alpha Corp'})

    def test_salesperson_sees_only_their_own(self):
        names = {c['company_name'] for c in self.client_for(self.sales_a).get('/api/v1/customers/').json()}
        self.assertEqual(names, {'Alpha Corp'})

    def test_admin_sees_everything(self):
        names = {c['company_name'] for c in self.client_for(self.admin).get('/api/v1/customers/').json()}
        self.assertEqual(names, {'Alpha Corp', 'Beta Corp'})

    def test_funnel_is_scoped(self):
        SalesFunnel.objects.create(
            date_created=timezone.now().date(), company_name='Alpha Corp',
            requirement_description='x', cost=Decimal('100'), retail=Decimal('200'),
            stage='quoted', salesperson=self.sales_a, customer=self.cust_a,
        )
        SalesFunnel.objects.create(
            date_created=timezone.now().date(), company_name='Beta Corp',
            requirement_description='y', cost=Decimal('100'), retail=Decimal('300'),
            stage='quoted', salesperson=self.sales_b, customer=self.cust_b,
        )
        rows = self.client_for(self.sales_a).get('/api/v1/funnel/').json()
        self.assertEqual([r['company_name'] for r in rows], ['Alpha Corp'])


class CustomerRequestApprovalTests(ApiTestBase):

    def setUp(self):
        super().setUp()
        self.request_b = CustomerCreateRequest.objects.create(
            company_name='Gamma Corp', contact_person_name='Gia G',
            email='gia@gamma.test', requested_by=self.sales_b, status='pending',
        )

    def test_avp_cannot_approve_another_teams_request(self):
        """Previously any AVP could approve any pending request company-wide."""
        response = self.client_for(self.avp_a).post(
            f'/api/v1/customer-requests/{self.request_b.id}/approve/'
        )
        self.assertIn(response.status_code, (403, 404))
        self.request_b.refresh_from_db()
        self.assertEqual(self.request_b.status, 'pending')

    def test_owning_avp_can_approve(self):
        response = self.client_for(self.avp_b).post(
            f'/api/v1/customer-requests/{self.request_b.id}/approve/'
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.request_b.refresh_from_db()
        self.assertEqual(self.request_b.status, 'approved')

    def test_pending_queue_is_scoped_to_own_team(self):
        ids = [r['id'] for r in self.client_for(self.avp_a).get('/api/v1/customer-requests/pending/').json()]
        self.assertNotIn(self.request_b.id, ids)

    def test_salesperson_cannot_see_others_requests(self):
        ids = [r['id'] for r in self.client_for(self.sales_a).get('/api/v1/customer-requests/').json()]
        self.assertNotIn(self.request_b.id, ids)


class ActivityEndpointTests(ApiTestBase):

    def setUp(self):
        super().setUp()
        self.activity = SalesActivity.objects.create(
            title='Call Alpha', activity_type=self.activity_type,
            customer=self.cust_a, salesperson=self.sales_a,
            status='planned', priority='medium',
            scheduled_start=timezone.now() + timezone.timedelta(hours=1),
        )

    def test_activity_types_endpoint(self):
        """Android hardcoded `activityType = 1` because this did not exist."""
        response = self.client_for(self.sales_a).get('/api/v1/activity-types/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([t['name'] for t in response.json()], ['Call'])

    def test_complete_marks_activity_done_and_stamps_times(self):
        response = self.client_for(self.sales_a).post(
            f'/api/v1/activities/{self.activity.id}/complete/',
            {'notes': 'Spoke to Ann.'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.status, 'completed')
        self.assertIsNotNone(self.activity.actual_end)
        self.assertIn('Spoke to Ann.', self.activity.notes)

    def test_complete_is_rejected_twice(self):
        client = self.client_for(self.sales_a)
        client.post(f'/api/v1/activities/{self.activity.id}/complete/', {}, format='json')
        again = client.post(f'/api/v1/activities/{self.activity.id}/complete/', {}, format='json')
        self.assertEqual(again.status_code, 400)

    def test_patch_updates_and_writes_an_audit_log(self):
        response = self.client_for(self.sales_a).patch(
            f'/api/v1/activities/{self.activity.id}/',
            {'title': 'Call Alpha (rescheduled)', 'priority': 'high'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.title, 'Call Alpha (rescheduled)')
        self.assertTrue(self.activity.logs.filter(action='updated').exists())

    def test_other_salesperson_cannot_touch_the_activity(self):
        response = self.client_for(self.sales_b).patch(
            f'/api/v1/activities/{self.activity.id}/', {'title': 'hijacked'}, format='json'
        )
        self.assertIn(response.status_code, (403, 404))

    def test_upcoming_filter(self):
        response = self.client_for(self.sales_a).get('/api/v1/activities/?upcoming=true')
        self.assertEqual(len(response.json()), 1)


class ProposalEndpointTests(ApiTestBase):

    def setUp(self):
        super().setUp()
        self.proposal = Proposal.objects.create(
            customer=self.cust_a, created_by=self.sales_a, subject='Alpha quote',
        )

    def test_pdf_endpoint_returns_a_pdf(self):
        response = self.client_for(self.sales_a).get(f'/api/v1/proposals/{self.proposal.id}/pdf/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF'))

    def test_pdf_is_scoped(self):
        response = self.client_for(self.sales_b).get(f'/api/v1/proposals/{self.proposal.id}/pdf/')
        self.assertEqual(response.status_code, 404)

    def test_rejected_proposal_cannot_be_approved(self):
        """
        Regression: rejection left later steps 'pending', so the next approver
        could still act and flip the proposal back to approved.
        """
        self.proposal.approval_required = True
        self.proposal.approval_status = 'pending'
        self.proposal.save()
        ProposalApprovalStep.objects.create(proposal=self.proposal, level=1, approver=self.sup_a)
        ProposalApprovalStep.objects.create(proposal=self.proposal, level=2, approver=self.avp_a)

        reject = self.client_for(self.sup_a).post(
            f'/api/v1/proposals/{self.proposal.id}/reject/', {'comment': 'no'}, format='json'
        )
        self.assertEqual(reject.status_code, 200, reject.content)

        approve = self.client_for(self.avp_a).post(
            f'/api/v1/proposals/{self.proposal.id}/approve/', {'comment': 'yes'}, format='json'
        )
        self.assertEqual(approve.status_code, 409)

        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.approval_status, 'rejected')

    def test_downstream_steps_are_cancelled_on_rejection(self):
        self.proposal.approval_required = True
        self.proposal.approval_status = 'pending'
        self.proposal.save()
        ProposalApprovalStep.objects.create(proposal=self.proposal, level=1, approver=self.sup_a)
        step2 = ProposalApprovalStep.objects.create(proposal=self.proposal, level=2, approver=self.avp_a)

        self.client_for(self.sup_a).post(
            f'/api/v1/proposals/{self.proposal.id}/reject/', {'comment': 'no'}, format='json'
        )
        step2.refresh_from_db()
        self.assertEqual(step2.status, 'cancelled')


class DashboardTests(ApiTestBase):

    def test_dashboard_returns_scoped_rollup(self):
        response = self.client_for(self.sales_a).get('/api/v1/dashboard/')
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()

        for key in ('user', 'customers', 'funnel', 'proposals', 'activities',
                    'customer_requests', 'upcoming_activities', 'recent_proposals'):
            self.assertIn(key, body)

        # Scoped: sales_a owns exactly one customer.
        self.assertEqual(body['customers']['total'], 1)
        self.assertEqual(len(body['funnel']['stages']), len(SalesFunnel.FUNNEL_STAGES))

    def test_dashboard_requires_auth(self):
        self.assertEqual(APIClient().get('/api/v1/dashboard/').status_code, 401)


class AuthFlowTests(ApiTestBase):

    def test_password_login_returns_a_token_when_mfa_not_required(self):
        response = APIClient().post(
            '/api/v1/api-token-auth/',
            {'username': 'sales_a', 'password': 'Testpass!2345'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertIn('token', body)
        self.assertEqual(body['role'], 'salesperson')
        self.assertEqual(body['username'], 'sales_a')

    def test_logout_revokes_the_token(self):
        client = self.client_for(self.sales_a)
        self.assertEqual(client.post('/api/v1/logout/').status_code, 200)
        self.assertFalse(Token.objects.filter(user=self.sales_a).exists())
        # The old credentials must stop working.
        self.assertEqual(client.get('/api/v1/customers/').status_code, 401)

    def test_bad_password_is_rejected(self):
        response = APIClient().post(
            '/api/v1/api-token-auth/',
            {'username': 'sales_a', 'password': 'wrong'}, format='json',
        )
        self.assertEqual(response.status_code, 400)


class MfaAuthFlowTests(ApiTestBase):
    """
    Token auth used to hand out a permanent API token for a password alone,
    bypassing the TOTP that MFARequiredMiddleware enforces on the web.
    """

    def _enrol_totp(self, user):
        from allauth.mfa.totp import TOTP, generate_totp_secret
        secret = generate_totp_secret()
        TOTP.activate(user, secret)
        return secret

    def _current_code(self, secret):
        from allauth.mfa.totp import format_hotp_value, hotp_counter_from_time, hotp_value
        return format_hotp_value(hotp_value(secret, hotp_counter_from_time()))

    def _enable_site_mfa(self):
        from core.models import SiteSetting
        setting = SiteSetting.objects.first() or SiteSetting()
        setting.mfa_required = True
        setting.save()

    def test_enrolled_user_is_challenged_instead_of_handed_a_token(self):
        self._enrol_totp(self.sales_a)
        response = APIClient().post(
            '/api/v1/api-token-auth/',
            {'username': 'sales_a', 'password': 'Testpass!2345'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get('mfa_required'))
        self.assertIn('mfa_token', body)
        self.assertNotIn('token', body, 'password alone still yielded an API token')

    def test_valid_totp_code_completes_login(self):
        secret = self._enrol_totp(self.sales_a)
        client = APIClient()
        challenge = client.post(
            '/api/v1/api-token-auth/',
            {'username': 'sales_a', 'password': 'Testpass!2345'}, format='json',
        ).json()

        response = client.post(
            '/api/v1/api-token-auth/mfa/',
            {'mfa_token': challenge['mfa_token'], 'code': self._current_code(secret)},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn('token', response.json())

    def test_wrong_totp_code_is_rejected(self):
        self._enrol_totp(self.sales_a)
        client = APIClient()
        challenge = client.post(
            '/api/v1/api-token-auth/',
            {'username': 'sales_a', 'password': 'Testpass!2345'}, format='json',
        ).json()

        response = client.post(
            '/api/v1/api-token-auth/mfa/',
            {'mfa_token': challenge['mfa_token'], 'code': '000000'}, format='json',
        )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(Token.objects.filter(user=self.sales_a).exists())

    def test_mfa_token_is_not_usable_as_an_api_token(self):
        self._enrol_totp(self.sales_a)
        challenge = APIClient().post(
            '/api/v1/api-token-auth/',
            {'username': 'sales_a', 'password': 'Testpass!2345'}, format='json',
        ).json()

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {challenge['mfa_token']}")
        self.assertEqual(client.get('/api/v1/customers/').status_code, 401)

    def test_tampered_mfa_token_is_rejected(self):
        secret = self._enrol_totp(self.sales_a)
        challenge = APIClient().post(
            '/api/v1/api-token-auth/',
            {'username': 'sales_a', 'password': 'Testpass!2345'}, format='json',
        ).json()

        response = APIClient().post(
            '/api/v1/api-token-auth/mfa/',
            {'mfa_token': challenge['mfa_token'] + 'x', 'code': self._current_code(secret)},
            format='json',
        )
        self.assertEqual(response.status_code, 401)

    def test_site_wide_mfa_blocks_unenrolled_users_with_guidance(self):
        self._enable_site_mfa()
        response = APIClient().post(
            '/api/v1/api-token-auth/',
            {'username': 'sales_a', 'password': 'Testpass!2345'}, format='json',
        )
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertTrue(body.get('mfa_setup_required'))
        self.assertNotIn('token', body)

    def test_recovery_code_also_completes_login(self):
        from allauth.mfa.recovery_codes import RecoveryCodes
        self._enrol_totp(self.sales_a)
        authenticator = RecoveryCodes.activate(self.sales_a).instance
        code = authenticator.wrap().get_unused_codes()[0]

        client = APIClient()
        challenge = client.post(
            '/api/v1/api-token-auth/',
            {'username': 'sales_a', 'password': 'Testpass!2345'}, format='json',
        ).json()
        response = client.post(
            '/api/v1/api-token-auth/mfa/',
            {'mfa_token': challenge['mfa_token'], 'code': code}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn('token', response.json())


class ContractFixtureTests(ApiTestBase):
    """
    Dumps real API responses to /tmp/micrm-contract so the iOS client's Codable
    models can be decoded against them (MiCRM_iOS/Verify/run.sh). This is what
    catches serializer changes silently breaking the mobile apps.

    Skipped unless MICRM_DUMP_CONTRACT=1, so normal test runs stay hermetic.
    """

    def test_dump_contract_fixtures(self):
        import json
        import os

        if os.environ.get('MICRM_DUMP_CONTRACT') != '1':
            self.skipTest('set MICRM_DUMP_CONTRACT=1 to regenerate iOS contract fixtures')

        out = '/tmp/micrm-contract'
        os.makedirs(out, exist_ok=True)

        # Give every endpoint something non-trivial to serialise.
        SalesFunnel.objects.create(
            date_created=timezone.now().date(), company_name='Alpha Corp',
            requirement_description='Core switch refresh', cost=Decimal('300000'),
            retail=Decimal('1250000'), stage='quoted',
            salesperson=self.sales_a, customer=self.cust_a,
        )
        proposal = Proposal.objects.create(
            customer=self.cust_a, created_by=self.sales_a, subject='Core switch refresh',
        )
        ProposalApprovalStep.objects.create(proposal=proposal, level=1, approver=self.sup_a)
        SalesActivity.objects.create(
            title='Site visit', activity_type=self.activity_type, customer=self.cust_a,
            salesperson=self.sales_a, status='planned', priority='high',
            scheduled_start=timezone.now() + timezone.timedelta(days=1),
            scheduled_end=timezone.now() + timezone.timedelta(days=1, hours=1),
        )
        CustomerCreateRequest.objects.create(
            company_name='Gamma Corp', contact_person_name='Gia G',
            email='gia@gamma.test', requested_by=self.sales_a, status='pending',
        )

        client = self.client_for(self.sales_a)
        endpoints = {
            'dashboard': '/api/v1/dashboard/',
            'customers': '/api/v1/customers/',
            'customer_detail': f'/api/v1/customers/{self.cust_a.id}/',
            'customer_choices': '/api/v1/customers/choices/',
            'customer_requests_mine': '/api/v1/customer-requests/mine/',
            'funnel': '/api/v1/funnel/',
            'proposals': '/api/v1/proposals/',
            'proposal_detail': f'/api/v1/proposals/{proposal.id}/',
            'activities': '/api/v1/activities/',
            'activity_types': '/api/v1/activity-types/',
            'campaigns': '/api/v1/campaigns/',
            'me': '/api/v1/users/me/',
        }

        for name, url in endpoints.items():
            response = client.get(url)
            self.assertEqual(response.status_code, 200, f'{url} -> {response.status_code}')
            with open(os.path.join(out, f'{name}.json'), 'w') as handle:
                json.dump(response.json(), handle, indent=2)

        # Approval inbox, from the approver's side.
        proposal.approval_required = True
        proposal.approval_status = 'pending'
        proposal.save()
        response = self.client_for(self.sup_a).get('/api/v1/proposals/pending_approvals/')
        self.assertEqual(response.status_code, 200)
        with open(os.path.join(out, 'pending_approvals.json'), 'w') as handle:
            json.dump(response.json(), handle, indent=2)

        # Both auth shapes.
        anon = APIClient()
        with open(os.path.join(out, 'auth_password.json'), 'w') as handle:
            json.dump(anon.post('/api/v1/api-token-auth/', {
                'username': 'sales_b', 'password': 'Testpass!2345'
            }, format='json').json(), handle, indent=2)

        from allauth.mfa.totp import TOTP, generate_totp_secret
        TOTP.activate(self.sm_a, generate_totp_secret())
        with open(os.path.join(out, 'auth_mfa_challenge.json'), 'w') as handle:
            json.dump(anon.post('/api/v1/api-token-auth/', {
                'username': 'sm_a', 'password': 'Testpass!2345'
            }, format='json').json(), handle, indent=2)

        print(f'\nWrote {len(endpoints) + 3} contract fixtures to {out}')
