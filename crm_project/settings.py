"""
Django settings for crm_project project.
"""
import os
from pathlib import Path
from decouple import config, Csv

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')

DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='127.0.0.1,localhost,10.10.10.125', cast=Csv())

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.sites',
    # Third-party apps
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'crispy_forms',
    'crispy_bootstrap5',
    # allauth (must come BEFORE mfa)
    'allauth',
    'allauth.account',
    'allauth.mfa',
    # Local apps
    'users',
    'customers',
    'teams',
    'core',
    'sales_funnel',
    'sales_monitoring',
    'lead_generation',
    'file_sharing',
    'sales_proposals',
    'customer_service',
    'gamification',
    'mass_mailing',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'core.middleware.MFARequiredMiddleware',
    'users.middleware.UserActivityMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'crm_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'gamification.context_processors.gamification_status',
                'customers.context_processors.customer_request_notifications',
                'sales_proposals.context_processors.proposal_approval_notifications',
                'mass_mailing.context_processors.marketing_updates',
            ],
        },
    },
]

WSGI_APPLICATION = 'crm_project.wsgi.application'

# ---------------------------------------------------------------------------
# Database — MariaDB (production) / SQLite (local dev fallback)
# ---------------------------------------------------------------------------
# Set DB_ENGINE=mariadb in your .env for production.
# Leave it unset (or set DB_ENGINE=sqlite3) for local development.

DB_ENGINE = config('DB_ENGINE', default='sqlite3').lower()

if DB_ENGINE in ['mariadb', 'mysql']:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': config('DB_NAME', default='mi_crm'),
            'USER': config('DB_USER', default='mi_crm_user'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST': config('DB_HOST', default='127.0.0.1'),
            'PORT': config('DB_PORT', default='3306'),
            'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=60, cast=int),
            'OPTIONS': {
                'charset': 'utf8mb4',
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }
else:
    # SQLite — development only, never use in production
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': config('SQLITE_PATH', default=str(BASE_DIR / 'db.sqlite3')),
            'OPTIONS': {
                'timeout': 30,  # Wait up to 30 seconds for lock release before raising OperationalError
            },
        }
    }

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Manila'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & Media files
# ---------------------------------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB (stream to disk above this)
# Max request body Django will accept. Raised to 150 MB so large shared files
# (e.g. the company-wide Android APK) can be uploaded. NOTE: the front-end web
# server (nginx) also caps the body via `client_max_body_size` — that must be
# raised to match or uploads are rejected with HTTP 413 before reaching Django.
DATA_UPLOAD_MAX_MEMORY_SIZE = 150 * 1024 * 1024  # 150 MB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# Passcode required to run the Sales Funnel "Clear Stage" bulk cleanup on
# PRODUCTION (DEBUG=False). Leave blank to DISABLE Clear Stage in production
# entirely. Ignored on dev/test machines (DEBUG=True), where it runs freely.
FUNNEL_CLEAR_STAGE_CODE = config('FUNNEL_CLEAR_STAGE_CODE', default='')

# ---------------------------------------------------------------------------
# Active Users Widget
# ---------------------------------------------------------------------------
# A user is considered "online" if their last_activity is within this window.
# Powered by UserActivityMiddleware which updates last_activity on every request.
ONLINE_THRESHOLD_MINUTES = 15

# ---------------------------------------------------------------------------
# Brute Force Protection
# ---------------------------------------------------------------------------
# Account is locked after MAX_FAILED_LOGIN_ATTEMPTS within FAILED_LOGIN_WINDOW_MINUTES.
# Lockout lasts ACCOUNT_LOCKOUT_MINUTES. Admin can unlock via Django admin.
MAX_FAILED_LOGIN_ATTEMPTS = config('MAX_FAILED_LOGIN_ATTEMPTS', default=5, cast=int)
FAILED_LOGIN_WINDOW_MINUTES = config('FAILED_LOGIN_WINDOW_MINUTES', default=15, cast=int)
ACCOUNT_LOCKOUT_MINUTES = config('ACCOUNT_LOCKOUT_MINUTES', default=30, cast=int)

# ---------------------------------------------------------------------------
# Default primary key
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = 'users.User'

# Both backends enforce the failed-login lockout. Do NOT swap either for its
# un-wrapped upstream class: authenticate() returns the first backend that
# yields a user, so an unguarded backend anywhere in this list defeats the
# lockout entirely.
AUTHENTICATION_BACKENDS = [
    'users.backends.LockoutAwareBackend',           # ModelBackend + lockout
    'users.backends.LockoutAwareAllauthBackend',    # allauth backend + lockout
]

SITE_ID = 1

ACCOUNT_LOGIN_METHODS = {'email', 'username'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'none'

# Account/reset emails come from a dedicated no-reply mailbox (via MiCrmAccountAdapter),
# WITHOUT changing DEFAULT_FROM_EMAIL used by the rest of the app's emails.
ACCOUNT_ADAPTER = 'users.adapters.MiCrmAccountAdapter'
ACCOUNT_DEFAULT_FROM_EMAIL = config('ACCOUNT_DEFAULT_FROM_EMAIL', default='no-reply@microimageph.com')
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_UNIQUE_EMAIL = True

# --- Password reset hardening (internet-facing) ---
# Never reveal whether an email/username exists (anti-enumeration). allauth shows
# the same neutral "we've sent an email if the account exists" message either way.
ACCOUNT_PREVENT_ENUMERATION = True

# Rate limit sensitive actions to resist email-bombing, enumeration probing, and
# SMTP abuse on the public reset endpoint. Format: "<count>/<period>/<scope>".
#   reset_password        -> per-IP throttle on the reset REQUEST form
#   reset_password_from_key -> per-IP throttle on the token-confirm page
#   login / login_failed  -> defense in depth alongside the LockoutAwareBackend
ACCOUNT_RATE_LIMITS = {
    'reset_password': '5/m/ip',
    'reset_password_email': '3/5m/key',   # per target email address
    'reset_password_from_key': '10/m/ip',
    'login': '30/m/ip',
    'login_failed': '5/5m/ip',
}

# MFA
MFA_SUPPORTED_TYPES = ['totp', 'recovery_codes']
# Issuer name shown in authenticator apps (e.g. Microsoft/Google Authenticator).
# Without this, allauth falls back to the Sites framework domain ("example.com").
MFA_TOTP_ISSUER = 'MI CRM'

# ---------------------------------------------------------------------------
# Crispy Forms
# ---------------------------------------------------------------------------
CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10,
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# In production set CORS_ALLOW_ALL_ORIGINS=False and list trusted origins below.
CORS_ALLOW_ALL_ORIGINS = config('CORS_ALLOW_ALL_ORIGINS', default=False, cast=bool)
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='',
    cast=Csv(),
)

# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'

# ---------------------------------------------------------------------------
# Email (SMTP)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='email.microimageph.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='crm_sales@microimageph.com')
# SECURITY: no plaintext default — the SMTP password must come from the environment
# (.env / server env). If it is unset (e.g. local dev), we fall back to the
# file-based email backend below instead of shipping a real credential in source.
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='sales@microimageph.com')

# Fall back to file-based backend when SMTP is not configured (local dev) —
# i.e. when either the user or the password is missing.
if not EMAIL_HOST_USER or not EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
    EMAIL_FILE_PATH = BASE_DIR / 'sent_emails'

# ---------------------------------------------------------------------------
# Company info (used in email templates)
# ---------------------------------------------------------------------------
COMPANY_NAME = 'MICRO IMAGE INTERNATIONAL CORP.'
COMPANY_OFFICE_PHONE = '8-840-4323'
COMPANY_ADDRESS = (
    'Unit 53, 62 & 101 Legaspi Suites Building, 178 Salcedo St., '
    'Legaspi Village, Makati City 1229'
)
COMPANY_WEBSITE_URL = 'https://www.microimageph.com'
COMPANY_WEBSITE_LABEL = 'www.microimageph.com'
COMPANY_FACEBOOK_URL = 'https://www.facebook.com/MicroImagePh'
COMPANY_INSTAGRAM_URL = 'https://www.instagram.com/MicroImagePh'
COMPANY_X_URL = 'https://twitter.com/MicroImagePh'
COMPANY_LINKEDIN_URL = 'https://www.linkedin.com/company/MicroImagePh'

# ---------------------------------------------------------------------------
# Redmine integration
# ---------------------------------------------------------------------------
REDMINE_URL = config('REDMINE_URL', default='http://10.30.30.131')
REDMINE_USERNAME = config('REDMINE_USERNAME', default='customer_service')
REDMINE_API_KEY = config('REDMINE_API_KEY', default='')
REDMINE_PROJECT_ID = config('REDMINE_PROJECT_ID', default=14, cast=int)
REDMINE_TRACKER_ID = config('REDMINE_TRACKER_ID', default=7, cast=int)

# ---------------------------------------------------------------------------
# Site URL (for email links and absolute URLs)
# ---------------------------------------------------------------------------
# Used for generating absolute URLs in emails (unsubscribe, interested buttons, etc.)
# Set this to your production domain in production.
# Examples:
#   Development: http://127.0.0.1:8000 or http://10.10.10.125:8001
#   Production:  https://crm.microimageph.com
SITE_URL = config('SITE_URL', default='http://127.0.0.1:8000')

# ---------------------------------------------------------------------------
# Production security hardening
# These are safe to enable once the site runs on HTTPS.
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000          # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
