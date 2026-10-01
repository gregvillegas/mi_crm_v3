from datetime import timedelta

from django.conf import settings
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.utils.module_loading import import_string
from django.contrib.auth import authenticate, get_user_model
from unittest.mock import patch, MagicMock

from users.models import FailedLoginAttempt
from users.signals import is_account_locked

User = get_user_model()


class MFATestCase(TestCase):
    """Tests for Two-Factor Authentication (MFA) functionality."""
    
    def setUp(self):
        """Set up test users."""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            email='test@example.com',
            first_name='Test',
            last_name='User'
        )
        self.admin_user = User.objects.create_user(
            username='adminuser',
            password='adminpass123',
            email='admin@example.com',
            first_name='Admin',
            last_name='User',
            role='admin'
        )
        self.client = Client()
    
    def test_mfa_index_url_exists(self):
        """Test that MFA index URL is accessible."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/accounts/2fa/')
        self.assertEqual(response.status_code, 200)
    
    def test_mfa_activate_totp_url_exists(self):
        """Test that MFA TOTP activation URL is accessible."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/accounts/2fa/totp/activate/')
        self.assertEqual(response.status_code, 200)
    
    def test_profile_shows_mfa_section(self):
        """Test that MFA section appears on profile page."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Two-Factor Authentication', status_code=200)
        self.assertContains(response, 'Security', status_code=200)
    
    def test_mfa_not_enabled_by_default(self):
        """Test that MFA is not enabled for new users by default."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        # Should show "Not Enabled" badge for new users
        self.assertContains(response, 'Not Enabled', status_code=200)
    
    def test_login_page_has_mfa_branding(self):
        """Test that login page shows MFA branding."""
        response = self.client.get('/login/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Two-Factor Authentication', status_code=200)
    
    def test_mfa_urls_require_authentication(self):
        """Test that MFA URLs require login."""
        response = self.client.get('/accounts/2fa/')
        # Should redirect to login
        self.assertIn(response.status_code, [302, 403])
    
    @patch('allauth.mfa.models.Authenticator.objects.filter')
    def test_profile_shows_enabled_when_mfa_active(self, mock_filter):
        """Test that profile shows MFA enabled when user has TOTP configured."""
        # Mock the filter to return a non-empty queryset
        mock_queryset = MagicMock()
        mock_queryset.exists.return_value = True
        mock_filter.return_value = mock_queryset
        
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        # Should show "Enabled" badge
        self.assertContains(response, 'Enabled', status_code=200)


class MFAIntegrationTestCase(TestCase):
    """Integration tests for MFA workflow."""
    
    def setUp(self):
        """Set up test user."""
        self.user = User.objects.create_user(
            username='mfauser',
            password='mfapass123',
            email='mfa@example.com',
            first_name='MFA',
            last_name='User'
        )
        self.client = Client()
    
    def test_api_token_auth_still_works(self):
        """Test that API token authentication is not affected by MFA."""
        from rest_framework.authtoken.models import Token
        Token.objects.create(user=self.user)
        
        # API token auth should work independently of session-based MFA
        response = self.client.post('/api/v1/api-token-auth/', {
            'username': 'mfauser',
            'password': 'mfapass123'
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('token', response.json())
    
    def test_login_redirect_preserved(self):
        """Test that login redirects work correctly with MFA."""
        # Ensure login page loads
        response = self.client.get('/login/')
        self.assertEqual(response.status_code, 200)
        
        # Login should work
        response = self.client.post('/login/', {
            'username': 'mfauser',
            'password': 'mfapass123'
        }, follow=True)
        # Should redirect to home or MFA verification
        self.assertIn(response.status_code, [200, 302])


class LoginLockoutTestCase(TestCase):
    """
    Regression tests for the failed-login lockout.

    The lockout was previously enforced on only one of the two configured
    authentication backends. Because django.contrib.auth.authenticate() returns
    the first backend that yields a user, the unguarded allauth backend still
    authenticated locked accounts with a correct password.
    """

    PASSWORD = 'CorrectHorse!42'

    def setUp(self):
        self.user = User.objects.create_user(
            username='victim',
            email='victim@example.com',
            password=self.PASSWORD,
            role='salesperson',
        )
        self.client = Client()

    def _exhaust_attempts(self, username='victim'):
        limit = getattr(settings, 'MAX_FAILED_LOGIN_ATTEMPTS', 5)
        for _ in range(limit + 1):
            authenticate(request=None, username=username, password='wrong-password')
        locked, _ = is_account_locked(username)
        self.assertTrue(locked, 'precondition failed: account should be locked')

    def test_every_configured_backend_enforces_the_lockout(self):
        """No backend in the chain may authenticate a locked account."""
        self._exhaust_attempts()
        for path in settings.AUTHENTICATION_BACKENDS:
            backend = import_string(path)()
            self.assertIsNone(
                backend.authenticate(None, username='victim', password=self.PASSWORD),
                f'{path} authenticated a locked account',
            )

    def test_locked_account_rejected_with_correct_password(self):
        self._exhaust_attempts()
        self.assertIsNone(
            authenticate(request=None, username='victim', password=self.PASSWORD)
        )

    def test_locked_account_cannot_log_in_via_web(self):
        self._exhaust_attempts()
        response = self.client.post(
            reverse('account_login'),
            {'login': 'victim', 'password': self.PASSWORD},
        )
        # Re-renders the form (200) rather than redirecting to the site on success.
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_locked_account_cannot_obtain_api_token(self):
        self._exhaust_attempts()
        response = self.client.post(
            '/api/v1/api-token-auth/',
            {'username': 'victim', 'password': self.PASSWORD},
        )
        self.assertEqual(response.status_code, 400)

    def test_unlocked_account_still_authenticates(self):
        """The lockout must not break the normal path."""
        self.assertEqual(
            authenticate(request=None, username='victim', password=self.PASSWORD),
            self.user,
        )

    def test_lockout_lifts_once_the_window_passes(self):
        self._exhaust_attempts()
        stale = timezone.now() - timedelta(
            minutes=getattr(settings, 'FAILED_LOGIN_WINDOW_MINUTES', 15) + 1
        )
        FailedLoginAttempt.objects.filter(username='victim').update(timestamp=stale)
        self.assertEqual(
            authenticate(request=None, username='victim', password=self.PASSWORD),
            self.user,
        )


class LogoutMethodTestCase(TestCase):
    """Logout must be POST-only so third-party pages cannot force a logout."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='logoutuser', password='logoutpass123', email='lo@example.com'
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_get_logout_is_rejected(self):
        response = self.client.get(reverse('logout'))
        self.assertEqual(response.status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)

    def test_post_logout_signs_the_user_out(self):
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)
