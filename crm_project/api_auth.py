"""
Token authentication for the mobile clients, with MFA.

The plain DRF ObtainAuthToken view traded a password for a permanent API token,
which meant mobile completely bypassed the TOTP requirement that
core.middleware.MFARequiredMiddleware enforces on the web. This module adds the
second factor to the mobile flow:

    POST /api/v1/api-token-auth/       {username, password}
        -> {"token": ...}                                   (MFA not applicable)
        -> {"mfa_required": true, "mfa_token": "...", ...}  (second step needed)

    POST /api/v1/api-token-auth/mfa/   {mfa_token, code}
        -> {"token": ...}

The interim `mfa_token` is a signed, short-lived (5 min) blob — it is NOT an API
token and authenticates nothing on its own. Codes are verified through allauth's
own authenticator wrappers, so TOTP replay protection and recovery codes behave
exactly as they do on the web.
"""
from django.conf import settings
from django.core import signing
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from allauth.mfa.models import Authenticator
from allauth.mfa.utils import is_mfa_enabled

User = get_user_model()

MFA_TOKEN_SALT = 'micrm.api.mfa'
MFA_TOKEN_MAX_AGE = 300  # seconds


def mfa_is_required_for(user):
    """
    True when this user must present a second factor to obtain an API token.

    Mirrors the web rule: MFA matters only when the site-wide switch is on. A
    user who has TOTP enrolled is always challenged, switch or not — opting in
    should not be weaker on mobile than on the web.
    """
    if is_mfa_enabled(user):
        return True

    from core.models import SiteSetting
    setting = SiteSetting.objects.first()
    return bool(setting and setting.mfa_required)


def _user_payload(user, token):
    return {
        'token': token.key,
        'user_id': user.pk,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'role': user.role,
        'role_display': user.get_role_display(),
    }


def verify_mfa_code(user, code):
    """
    Validate a TOTP or recovery code against the user's enrolled authenticators.

    Delegates to allauth so single-use enforcement (TOTP replay cache, recovery
    code burn-down) is shared with the web login.
    """
    code = (code or '').strip().replace(' ', '')
    if not code:
        return False

    for authenticator in Authenticator.objects.filter(user=user):
        try:
            if authenticator.wrap().validate_code(code):
                authenticator.record_usage()
                return True
        except Exception:
            # A malformed authenticator row must not let the caller through.
            continue
    return False


class CustomAuthToken(ObtainAuthToken):
    """Step 1: exchange username + password for a token, or an MFA challenge."""

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']

        if mfa_is_required_for(user):
            if not is_mfa_enabled(user):
                # Site requires MFA but this account has not enrolled. Enrolment
                # needs the QR flow, which only the web UI implements.
                return Response(
                    {
                        'detail': (
                            'Two-factor authentication is required but not yet set up '
                            'on your account. Please sign in on the CRM website to '
                            'enrol an authenticator app, then sign in here.'
                        ),
                        'mfa_setup_required': True,
                        'setup_url': f"{getattr(settings, 'SITE_URL', '')}/accounts/2fa/",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            mfa_token = signing.dumps({'user_id': user.pk}, salt=MFA_TOKEN_SALT)
            return Response({
                'mfa_required': True,
                'mfa_token': mfa_token,
                'expires_in': MFA_TOKEN_MAX_AGE,
                'detail': 'Enter the 6-digit code from your authenticator app.',
            })

        token, _ = Token.objects.get_or_create(user=user)
        return Response(_user_payload(user, token))


class MfaAuthToken(APIView):
    """Step 2: exchange the interim MFA token + a TOTP/recovery code for a token."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        mfa_token = request.data.get('mfa_token')
        code = request.data.get('code')

        if not mfa_token or not code:
            return Response(
                {'detail': 'Both mfa_token and code are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            data = signing.loads(mfa_token, salt=MFA_TOKEN_SALT, max_age=MFA_TOKEN_MAX_AGE)
        except signing.SignatureExpired:
            return Response(
                {'detail': 'This sign-in attempt expired. Please enter your password again.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except signing.BadSignature:
            return Response({'detail': 'Invalid sign-in token.'}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            user = User.objects.get(pk=data['user_id'], is_active=True)
        except User.DoesNotExist:
            return Response({'detail': 'Invalid sign-in token.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not verify_mfa_code(user, code):
            return Response(
                {'detail': 'That code is not valid. Check your authenticator app and try again.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        token, _ = Token.objects.get_or_create(user=user)
        return Response(_user_payload(user, token))


class LogoutView(APIView):
    """Revoke the caller's API token. The mobile clients had no way to do this."""

    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        Token.objects.filter(user=request.user).delete()
        return Response({'detail': 'Signed out.'})
