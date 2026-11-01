from django.contrib.auth.models import AbstractUser, Group as AuthGroup, Permission
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('avp', 'AVP'),
        ('supervisor', 'Supervisor'),
        ('salesperson', 'Corporate Account Manager'),
        ('vp', 'Vice President'),
        ('gm', 'General Manager'),
        ('president', 'President'),
        ('asm', 'Sales Manager'),
        ('sm', 'Sales Manager'),
        ('teamlead', 'Teamlead'),
        ('techmgr', 'Technical Manager'),
        ('asst_techmgr', 'Assistant Technical Manager'),
        ('technical_sales', 'Technical Sales'),
        ('marketing', 'Marketing'),
        ('warehouse', 'Warehouse'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='salesperson')
    initials = models.CharField(max_length=3, blank=True, help_text='3-letter initials for the user (e.g., JDO for John Doe)')
    mobile_number = models.CharField(max_length=20, blank=True, null=True, help_text='Mobile number of the user')
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True, help_text='Profile picture for the user')
    signature_image = models.ImageField(upload_to='signatures/', blank=True, null=True, help_text='Digital signature image for proposals')
    JOB_TITLE_CHOICES = (
        ('account_manager', 'Corporate Account Manager'),
        ('marketing_officer', 'Marketing Officer'),
        ('sales_supervisor', 'Sales Supervisor'),
        ('president', 'President'),
        ('vice_president', 'Vice President'),
        ('general_manager', 'General Manager'),
        ('assistant_vp', 'Assistant VP'),
        ('sales_manager', 'Sales Manager'),
        ('accounting_manager', 'Accounting Manager'),
        ('operation_manager', 'Operation Manager'),
        ('cto', 'CTO'),
        ('ceo', 'CEO'),
        ('chairman', 'Chairman'),
        ('warehouse_supervisor', 'Warehouse Supervisor'),
        ('purchasing_supervisor', 'Purchasing Supervisor'),
        ('technical_manager', 'Technical Manager'),
        ('assistant_technical_manager', 'Assistant Technical Manager'),
        ('technical_sales', 'Technical Sales'),
        ('sr_teamlead', 'Sr. Teamlead'),
        ('purchasing_staff', 'Purchasing Staff'),
        ('accounting_staff', 'Accounting Staff'),
        ('warehouse_staff', 'Warehouse Staff'),
        ('hr_officer', 'HR Officer'),
    )
    job_title = models.CharField(max_length=50, choices=JOB_TITLE_CHOICES, blank=True)
    last_activity = models.DateTimeField(null=True, blank=True, help_text='Timestamp of last user activity')
    is_active = models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.')

    # --- Technical Sales scoping flags -------------------------------------
    # When True, a Technical Sales user covers the customers of ALL teams that
    # have a Technical Manager (the "one Technical Sales person handles both
    # Team A and Team B" case). When False, coverage comes from the teams the
    # user is explicitly attached to via Team.technical_sales.
    handles_all_technical_teams = models.BooleanField(
        default=False,
        help_text='Technical Sales only: cover every team that has a Technical Manager (single-person setup).',
    )
    # When True, this Technical Sales user has "mastered" proposal creation and
    # their proposals no longer require Technical Manager approval before being
    # sent. When False, every proposal they create requires approval.
    ts_approval_exempt = models.BooleanField(
        default=False,
        help_text='Technical Sales only: proposals no longer require Technical Manager approval.',
    )

    # Add related_name to resolve clashes with the default User model
    groups = models.ManyToManyField(
        AuthGroup,
        verbose_name='groups',
        blank=True,
        help_text=(
            'The groups this user belongs to. A user will get all permissions '
            'granted to each of their groups.'
        ),
        related_name="custom_user_set", # <--- FIX
        related_query_name="user",
    )
    user_permissions = models.ManyToManyField(
        Permission,
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name="custom_user_set", # <--- FIX
        related_query_name="user",
    )

class UserActivityLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='user_activity_logs')
    path = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'User Activity Log'
        verbose_name_plural = 'User Activity Logs'

    def __str__(self):
        return f"{self.user.username} - {self.method} {self.path} at {self.timestamp}"


class FailedLoginAttempt(models.Model):
    """
    Audit log for failed login attempts — required for Data Privacy Act (R.A. 10173) compliance.
    Records every authentication failure including username tried, IP, user agent, and timestamp.
    """
    username = models.CharField(max_length=150, help_text='Username or email that was attempted')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(
        max_length=50,
        default='invalid_credentials',
        choices=[
            ('invalid_credentials', 'Invalid Credentials'),
            ('account_disabled', 'Account Disabled'),
            ('mfa_failed', 'MFA Verification Failed'),
            ('account_locked', 'Account Locked'),
        ],
    )

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Failed Login Attempt'
        verbose_name_plural = 'Failed Login Attempts'
        indexes = [
            models.Index(fields=['username', '-timestamp']),
            models.Index(fields=['ip_address', '-timestamp']),
            models.Index(fields=['-timestamp']),
        ]

    def __str__(self):
        return f"{self.username} from {self.ip_address} at {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"


class PasswordResetAudit(models.Model):
    """
    Audit log for password-reset and MFA-reset activity — supports abuse detection
    on the internet-facing app and DPA (R.A. 10173) accountability.

    Records both self-service reset events and admin-initiated actions. For admin
    actions, `performed_by` is the admin; `target_user` is the affected account.
    """
    ACTION_CHOICES = [
        ('self_request', 'Self-service reset requested'),
        ('self_completed', 'Self-service reset completed'),
        ('admin_send_link', 'Admin sent reset link'),
        ('admin_reset_mfa', 'Admin reset MFA'),
    ]

    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    target_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='password_reset_events',
        help_text='The account the reset/MFA action applies to.',
    )
    target_identifier = models.CharField(
        max_length=254, blank=True,
        help_text='Email/username entered (kept even if no account matched, for abuse detection).',
    )
    performed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='password_reset_actions_performed',
        help_text='Admin who performed an admin-initiated action (null for self-service).',
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Password Reset Audit'
        verbose_name_plural = 'Password Reset Audit'
        indexes = [
            models.Index(fields=['action', '-timestamp']),
            models.Index(fields=['ip_address', '-timestamp']),
            models.Index(fields=['-timestamp']),
        ]

    def __str__(self):
        who = self.target_user or self.target_identifier or 'unknown'
        return f"{self.get_action_display()} — {who} at {self.timestamp:%Y-%m-%d %H:%M:%S}"
