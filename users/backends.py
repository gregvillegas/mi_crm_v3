"""
Authentication backends with brute force protection.

IMPORTANT: every backend listed in settings.AUTHENTICATION_BACKENDS must refuse
locked accounts. django.contrib.auth.authenticate() walks the backend list and
returns the first backend that yields a user, so a lockout check on only one
backend is no protection at all — a backend further down the chain will happily
authenticate the same locked account.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from allauth.account.auth_backends import AuthenticationBackend as AllauthBackend

from .signals import is_account_locked

User = get_user_model()


class LockoutMixin:
    """
    Refuses to authenticate an account that is currently locked out.

    Mix into every concrete backend rather than relying on a single gatekeeper
    backend — see the module docstring for why.
    """

    def authenticate(self, request, **credentials):
        # Mirror the key precedence used by users.signals.log_failed_login so the
        # identifier we check matches the one the failure counter is keyed on.
        identifier = (
            credentials.get('username')
            or credentials.get('login')
            or credentials.get('email')
        )
        if not identifier:
            return None

        # Check lockout BEFORE attempting password verification.
        locked, _minutes_remaining = is_account_locked(identifier)
        if locked:
            # Run the password hasher anyway so a locked account costs the same
            # time to reject as a wrong password — otherwise the response time
            # leaks whether an account is locked (and therefore that it exists).
            password = credentials.get('password')
            if password:
                User().set_password(password)
            # Returning None = authentication fails. The user_login_failed
            # signal logs it with reason='account_locked'.
            return None

        return super().authenticate(request, **credentials)


class LockoutAwareBackend(LockoutMixin, ModelBackend):
    """Django's ModelBackend (admin, DRF token auth) + lockout enforcement."""


class LockoutAwareAllauthBackend(LockoutMixin, AllauthBackend):
    """allauth's AuthenticationBackend (web login) + lockout enforcement."""
