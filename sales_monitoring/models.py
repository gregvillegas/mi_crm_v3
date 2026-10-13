from django.db import models
from django.utils import timezone
from users.models import User
from customers.models import Customer
from teams.models import Group
import json

class ActivityType(models.Model):
    """Predefined types of sales activities"""
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, default='fas fa-circle', help_text='FontAwesome icon class')
    color = models.CharField(max_length=20, default='primary', help_text='Bootstrap color class')
    is_active = models.BooleanField(default=True)
    requires_customer = models.BooleanField(default=True, help_text='Whether this activity type requires a customer association')
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
        
    def __str__(self):
        return self.name

class SalesActivity(models.Model):
    """Individual sales activities performed by salespeople"""
    CLIENT_MEETING_TYPE_NAMES = {'client meeting', 'meeting', 'client call'}
    
    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('postponed', 'Postponed'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    # Basic Information
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    activity_type = models.ForeignKey(ActivityType, on_delete=models.CASCADE, related_name='activities')
    
    # People involved
    salesperson = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sales_activities',
                                  limit_choices_to={'role': 'salesperson'})
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='activities',
                               null=True, blank=True)
    
    # Activity details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    
    # Timing
    scheduled_start = models.DateTimeField(null=True, blank=True)
    scheduled_end = models.DateTimeField(null=True, blank=True)
    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end = models.DateTimeField(null=True, blank=True)
    
    # Additional fields for specific activity types
    notes = models.TextField(blank=True, help_text='Notes and outcomes from the activity')
    follow_up_required = models.BooleanField(default=False)
    follow_up_date = models.DateTimeField(null=True, blank=True)
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # For supervisor oversight
    reviewed_by_supervisor = models.BooleanField(default=False)
    supervisor_notes = models.TextField(blank=True)
    supervisor_reviewed_at = models.DateTimeField(null=True, blank=True)
    engineer_required = models.BooleanField(
        default=False,
        help_text='Whether engineering support is required for this client meeting'
    )
    meeting_notification_sent_at = models.DateTimeField(null=True, blank=True)
    meeting_notification_sent_for = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Scheduled start datetime for which the last meeting reminder was sent'
    )
    
    class Meta:
        ordering = ['-scheduled_start', '-created_at']
        indexes = [
            models.Index(fields=['salesperson', '-scheduled_start']),
            models.Index(fields=['customer', '-scheduled_start']),
            models.Index(fields=['status', '-scheduled_start']),
            models.Index(fields=['activity_type', '-scheduled_start']),
            models.Index(fields=['reviewed_by_supervisor']),
        ]
        verbose_name = 'Sales Activity'
        verbose_name_plural = 'Sales Activities'
    
    def __str__(self):
        return f"{self.title} - {self.salesperson.username} ({self.get_status_display()})"
    
    @property
    def duration_minutes(self):
        """Calculate actual duration in minutes"""
        if self.actual_start and self.actual_end:
            delta = self.actual_end - self.actual_start
            return round(delta.total_seconds() / 60)
        return None
    
    @property
    def is_overdue(self):
        """Check if activity is overdue"""
        if self.scheduled_end and self.status not in ['completed', 'cancelled']:
            return timezone.now() > self.scheduled_end
        return False

    @property
    def is_client_meeting(self):
        """Identify activities that should use client meeting behavior."""
        activity_type_name = (self.activity_type.name or '').strip().lower() if self.activity_type_id else ''
        return activity_type_name in self.CLIENT_MEETING_TYPE_NAMES or hasattr(self, 'meeting_details')
    
    def mark_reviewed_by_supervisor(self, supervisor_user, notes='', engineer_required=None):
        """Mark activity as reviewed by supervisor"""
        self.reviewed_by_supervisor = True
        self.supervisor_notes = notes
        if engineer_required is not None:
            self.engineer_required = engineer_required
        self.supervisor_reviewed_at = timezone.now()
        self.save(update_fields=['reviewed_by_supervisor', 'supervisor_notes', 'engineer_required', 'supervisor_reviewed_at'])

    def mark_meeting_notification_sent(self):
        """Track that a meeting reminder email has been sent for the current schedule."""
        self.meeting_notification_sent_at = timezone.now()
        self.meeting_notification_sent_for = self.scheduled_start
        self.save(update_fields=['meeting_notification_sent_at', 'meeting_notification_sent_for'])

    def save(self, *args, **kwargs):
        """Override save to ensure timestamps are set correctly"""
        if self.status == 'completed' and not self.actual_end:
            self.actual_end = timezone.now()
        
        # Also ensure actual_start is set if missing when completed
        if self.status == 'completed' and not self.actual_start:
            self.actual_start = self.scheduled_start if self.scheduled_start else self.actual_end
            
        super().save(*args, **kwargs)

class CallActivity(models.Model):
    """Specific details for phone calls"""
    sales_activity = models.OneToOneField(SalesActivity, on_delete=models.CASCADE, related_name='call_details')
    phone_number = models.CharField(max_length=20)
    call_type = models.CharField(max_length=20, choices=[
        ('cold', 'Cold Call'),
        ('warm', 'Warm Call'),
        ('follow_up', 'Follow-up Call'),
        ('demo', 'Product Demo'),
        ('support', 'Customer Support'),
    ], default='cold')
    call_outcome = models.CharField(max_length=30, choices=[
        ('answered', 'Call Answered'),
        ('voicemail', 'Left Voicemail'),
        ('busy', 'Busy/No Answer'),
        ('wrong_number', 'Wrong Number'),
        ('not_interested', 'Not Interested'),
        ('interested', 'Interested'),
        ('meeting_scheduled', 'Meeting Scheduled'),
        ('proposal_requested', 'Proposal Requested'),
    ], blank=True)
    
    def __str__(self):
        return f"Call to {self.phone_number} - {self.get_call_type_display()}"

class MeetingActivity(models.Model):
    """Specific details for meetings"""
    sales_activity = models.OneToOneField(SalesActivity, on_delete=models.CASCADE, related_name='meeting_details')
    meeting_type = models.CharField(max_length=20, choices=[
        ('initial', 'Initial Meeting'),
        ('demo', 'Product Demo'),
        ('proposal', 'Proposal Presentation'),
        ('negotiation', 'Negotiation'),
        ('closing', 'Closing Meeting'),
        ('follow_up', 'Follow-up Meeting'),
    ], default='initial')
    location = models.CharField(max_length=200, blank=True)
    attendees = models.TextField(blank=True, help_text='List of attendees')
    meeting_outcome = models.CharField(max_length=30, choices=[
        ('successful', 'Successful'),
        ('needs_follow_up', 'Needs Follow-up'),
        ('not_interested', 'Not Interested'),
        ('proposal_requested', 'Proposal Requested'),
        ('deal_closed', 'Deal Closed'),
        ('cancelled', 'Cancelled'),
    ], blank=True)
    
    def __str__(self):
        return f"{self.get_meeting_type_display()} at {self.location or 'TBD'}"

class EmailActivity(models.Model):
    """Specific details for email communications"""
    sales_activity = models.OneToOneField(SalesActivity, on_delete=models.CASCADE, related_name='email_details')
    email_type = models.CharField(max_length=20, choices=[
        ('introduction', 'Introduction'),
        ('follow_up', 'Follow-up'),
        ('proposal', 'Proposal'),
        ('quote', 'Quote'),
        ('contract', 'Contract'),
        ('thank_you', 'Thank You'),
        ('newsletter', 'Newsletter'),
    ], default='introduction')
    subject = models.CharField(max_length=200)
    recipients = models.TextField(help_text='Email addresses of recipients')
    has_attachments = models.BooleanField(default=False)
    email_opened = models.BooleanField(default=False, help_text='Whether recipient opened the email')
    email_responded = models.BooleanField(default=False, help_text='Whether recipient responded')
    
    def __str__(self):
        return f"Email: {self.subject}"

class ProposalActivity(models.Model):
    """Specific details for proposals"""
    sales_activity = models.OneToOneField(SalesActivity, on_delete=models.CASCADE, related_name='proposal_details')
    proposal_title = models.CharField(max_length=200)
    proposal_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='PHP')
    proposal_status = models.CharField(max_length=20, choices=[
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('under_review', 'Under Review'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('negotiating', 'Negotiating'),
    ], default='draft')
    expected_decision_date = models.DateField(null=True, blank=True)
    win_probability = models.PositiveIntegerField(default=50, help_text='Probability of winning (0-100%)')
    
    def __str__(self):
        return f"Proposal: {self.proposal_title}"

class TaskActivity(models.Model):
    """Specific details for tasks"""
    sales_activity = models.OneToOneField(SalesActivity, on_delete=models.CASCADE, related_name='task_details')
    task_category = models.CharField(max_length=30, choices=[
        ('research', 'Customer Research'),
        ('preparation', 'Meeting Preparation'),
        ('documentation', 'Documentation'),
        ('follow_up', 'Follow-up Action'),
        ('administrative', 'Administrative'),
        ('training', 'Training/Learning'),
    ], default='administrative')
    estimated_hours = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    actual_hours = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    
    def __str__(self):
        return f"Task: {self.sales_activity.title}"

class ActivityLog(models.Model):
    """Log of all changes to sales activities for audit trail"""
    
    ACTION_CHOICES = [
        ('created', 'Activity Created'),
        ('updated', 'Activity Updated'),
        ('status_changed', 'Status Changed'),
        ('reviewed', 'Reviewed by Supervisor'),
        ('completed', 'Activity Completed'),
        ('cancelled', 'Activity Cancelled'),
    ]
    
    activity = models.ForeignKey(SalesActivity, on_delete=models.CASCADE, related_name='logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    description = models.TextField()
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='activity_logs')
    
    # Store previous and new values for tracking changes
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['activity', '-timestamp']),
            models.Index(fields=['changed_by', '-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.activity.title} - {self.get_action_display()} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
    
    @classmethod
    def log_activity_change(cls, activity, action, description, changed_by=None, old_value=None, new_value=None):
        """Convenience method to log an activity change"""
        return cls.objects.create(
            activity=activity,
            action=action,
            description=description,
            changed_by=changed_by,
            old_value=old_value,
            new_value=new_value
        )

class SupervisorReport(models.Model):
    """Supervisor reports on team performance"""
    
    REPORT_TYPE_CHOICES = [
        ('daily', 'Daily Report'),
        ('weekly', 'Weekly Report'),
        ('monthly', 'Monthly Report'),
        ('custom', 'Custom Period Report'),
    ]
    
    supervisor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='supervisor_reports',
                                 limit_choices_to={'role__in': ['supervisor', 'asm']})
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='reports')
    
    report_type = models.CharField(max_length=10, choices=REPORT_TYPE_CHOICES)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    
    # Report metrics
    total_activities = models.PositiveIntegerField(default=0)
    completed_activities = models.PositiveIntegerField(default=0)
    calls_made = models.PositiveIntegerField(default=0)
    meetings_held = models.PositiveIntegerField(default=0)
    emails_sent = models.PositiveIntegerField(default=0)
    proposals_sent = models.PositiveIntegerField(default=0)
    tasks_completed = models.PositiveIntegerField(default=0)
    
    # Performance metrics
    average_activity_completion_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    team_productivity_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['supervisor', '-created_at']),
            models.Index(fields=['group', '-created_at']),
            models.Index(fields=['period_start', 'period_end']),
        ]
    
    def __str__(self):
        return f"{self.get_report_type_display()} - {self.group.name} ({self.period_start.strftime('%Y-%m-%d')})"
    
    def generate_report_data(self):
        """Generate comprehensive report data"""
        # Get all salespeople in the group
        salespeople = User.objects.filter(
            team_membership__group=self.group,
            role='salesperson',
            is_active=True
        )
        
        report_data = {
            'period': {
                'start': self.period_start,
                'end': self.period_end,
            },
            'salespeople': [],
            'summary': {
                'total_salespeople': salespeople.count(),
                'total_activities': 0,
                'completed_activities': 0,
                'completion_rate': 0,
            }
        }
        
        total_activities = 0
        total_completed = 0
        
        for salesperson in salespeople:
            activities = SalesActivity.objects.filter(
                salesperson=salesperson,
                created_at__gte=self.period_start,
                created_at__lte=self.period_end
            )
            
            completed_activities = activities.filter(status='completed')
            
            salesperson_data = {
                'user': salesperson,
                'total_activities': activities.count(),
                'completed_activities': completed_activities.count(),
                'completion_rate': (completed_activities.count() / activities.count() * 100) if activities.count() > 0 else 0,
                'activities_by_type': {},
            }
            
            # Break down by activity type
            for activity_type in ActivityType.objects.filter(is_active=True):
                type_activities = activities.filter(activity_type=activity_type)
                type_completed = type_activities.filter(status='completed')
                
                salesperson_data['activities_by_type'][activity_type.name] = {
                    'total': type_activities.count(),
                    'completed': type_completed.count(),
                }
            
            report_data['salespeople'].append(salesperson_data)
            total_activities += activities.count()
            total_completed += completed_activities.count()
        
        # Update summary
        report_data['summary']['total_activities'] = total_activities
        report_data['summary']['completed_activities'] = total_completed
        report_data['summary']['completion_rate'] = (total_completed / total_activities * 100) if total_activities > 0 else 0
        
        return report_data

class ActivityReminder(models.Model):
    """Reminders for upcoming or overdue activities"""
    
    REMINDER_TYPE_CHOICES = [
        ('upcoming', 'Upcoming Activity'),
        ('overdue', 'Overdue Activity'),
        ('follow_up', 'Follow-up Required'),
        ('review_needed', 'Supervisor Review Needed'),
    ]
    
    activity = models.ForeignKey(SalesActivity, on_delete=models.CASCADE, related_name='reminders')
    reminder_type = models.CharField(max_length=20, choices=REMINDER_TYPE_CHOICES)
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activity_reminders')
    message = models.TextField()
    
    is_sent = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read']),
            models.Index(fields=['reminder_type', 'is_sent']),
        ]
    
    def __str__(self):
        return f"{self.get_reminder_type_display()} for {self.activity.title}"
    
    def mark_as_read(self):
        """Mark reminder as read"""
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=['is_read', 'read_at'])

class ProofOfConcept(models.Model):
    """Tracks Proof of Concept (POC) engagements with customers"""
    STATUS_CHOICES = [
        ('planned', 'Planned'),
        ('ongoing', 'Ongoing'),
        ('completed_success', 'Completed - Successful'),
        ('completed_fail', 'Completed - Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    title = models.CharField(max_length=200)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='pocs')
    sales_funnel = models.ForeignKey('sales_funnel.SalesFunnel', on_delete=models.SET_NULL, null=True, blank=True, related_name='pocs')
    
    lead_engineer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='led_pocs', limit_choices_to={'role__in': ['engineer', 'presales', 'salesperson']})
    salesperson = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sales_pocs')
    
    start_date = models.DateField()
    end_date = models.DateField()
    
    success_criteria = models.TextField(help_text="What defines a successful POC?")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planned')
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"POC: {self.title} - {self.customer.company_name}"


class FiscalYearSummary(models.Model):
    """
    A frozen, read-only snapshot of a fiscal year's performance for one scope
    (company / team / group / salesperson), captured at year-end.

    Performance across the app is normally computed LIVE from SalesFunnel rows,
    which can change after a year closes (edits, removals/restores, proposal
    amount changes). This model preserves the final numbers so a closed fiscal
    year stays stable and can be compared against the next year.
    See docs/FISCAL_YEAR_WORKFLOW.md.
    """
    SCOPE_COMPANY = 'company'
    SCOPE_TEAM = 'team'
    SCOPE_GROUP = 'group'
    SCOPE_SALESPERSON = 'salesperson'
    SCOPE_CHOICES = [
        (SCOPE_COMPANY, 'Company'),
        (SCOPE_TEAM, 'Team'),
        (SCOPE_GROUP, 'Group'),
        (SCOPE_SALESPERSON, 'Salesperson'),
    ]

    fiscal_year = models.IntegerField(
        help_text="Fiscal year named by the year it ends in (e.g. 2026 = Dec 2025 - Nov 2026)."
    )
    scope_type = models.CharField(max_length=20, choices=SCOPE_CHOICES)
    # The team/group/salesperson id this row summarizes. 0 for company-wide.
    scope_id = models.IntegerField(default=0)
    scope_name = models.CharField(
        max_length=200,
        help_text="Human-readable name of the scope at snapshot time (e.g. salesperson or group name)."
    )

    # Frozen performance metrics.
    won_count = models.IntegerField(default=0)
    lost_count = models.IntegerField(default=0)
    win_rate = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    total_revenue = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    total_profit = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    avg_deal_size = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    # 12 monthly profit figures, Dec..Nov, as a JSON list of strings/numbers.
    monthly_profit = models.JSONField(default=list, blank=True)

    # Frozen target/quota context so achievement % doesn't drift if quotas are
    # later edited. Null when no target applied to the scope.
    quota = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)

    # Provenance.
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fiscal_snapshots_generated'
    )
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('fiscal_year', 'scope_type', 'scope_id')
        ordering = ['-fiscal_year', 'scope_type', 'scope_name']
        indexes = [
            models.Index(fields=['fiscal_year', 'scope_type']),
        ]
        verbose_name = 'Fiscal Year Summary'
        verbose_name_plural = 'Fiscal Year Summaries'

    def __str__(self):
        return f"FY{self.fiscal_year} {self.get_scope_type_display()}: {self.scope_name}"

    @property
    def attainment_pct(self):
        """Profit vs frozen quota, as a percentage. None if no quota was set."""
        if self.quota and self.quota > 0:
            return float(self.total_profit / self.quota * 100)
        return None


class FiscalYearSnapshotLog(models.Model):
    """Audit trail for snapshot generation / regeneration of a fiscal year."""
    fiscal_year = models.IntegerField()
    action = models.CharField(max_length=20)  # 'created' | 'regenerated'
    scope_rows = models.IntegerField(default=0, help_text="Number of summary rows written.")
    performed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fiscal_snapshot_actions'
    )
    performed_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-performed_at']

    def __str__(self):
        return f"FY{self.fiscal_year} {self.action} ({self.scope_rows} rows) @ {self.performed_at:%Y-%m-%d}"
