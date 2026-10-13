from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import (
    ActivityType, SalesActivity, CallActivity, MeetingActivity, 
    EmailActivity, ProposalActivity, TaskActivity, ActivityLog,
    SupervisorReport, ActivityReminder, FiscalYearSummary, FiscalYearSnapshotLog
)

@admin.register(ActivityType)
class ActivityTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'icon_preview', 'color', 'requires_customer', 'is_active']
    list_filter = ['is_active', 'requires_customer']
    search_fields = ['name', 'description']
    list_editable = ['is_active']
    
    def icon_preview(self, obj):
        return format_html(
            '<i class="{} text-{}"></i> {}',
            obj.icon, obj.color, obj.icon
        )
    icon_preview.short_description = 'Icon Preview'

class CallActivityInline(admin.StackedInline):
    model = CallActivity
    extra = 0

class MeetingActivityInline(admin.StackedInline):
    model = MeetingActivity
    extra = 0

class EmailActivityInline(admin.StackedInline):
    model = EmailActivity
    extra = 0

class ProposalActivityInline(admin.StackedInline):
    model = ProposalActivity
    extra = 0

class TaskActivityInline(admin.StackedInline):
    model = TaskActivity
    extra = 0

class ActivityLogInline(admin.TabularInline):
    model = ActivityLog
    extra = 0
    readonly_fields = ['timestamp', 'changed_by', 'action', 'description']
    can_delete = False

@admin.register(SalesActivity)
class SalesActivityAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'activity_type', 'salesperson', 'customer', 'status', 
        'priority', 'scheduled_start', 'is_overdue_display', 'reviewed_display'
    ]
    list_filter = [
        'status', 'priority', 'activity_type', 'reviewed_by_supervisor',
        'salesperson__team_membership__group', 'created_at'
    ]
    search_fields = ['title', 'description', 'salesperson__username', 'customer__company_name']
    date_hierarchy = 'scheduled_start'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'activity_type')
        }),
        ('Assignment', {
            'fields': ('salesperson', 'customer')
        }),
        ('Status & Priority', {
            'fields': ('status', 'priority')
        }),
        ('Scheduling', {
            'fields': ('scheduled_start', 'scheduled_end', 'actual_start', 'actual_end')
        }),
        ('Follow-up', {
            'fields': ('follow_up_required', 'follow_up_date', 'notes')
        }),
        ('Supervisor Review', {
            'fields': ('reviewed_by_supervisor', 'supervisor_notes', 'supervisor_reviewed_at'),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = ['created_at', 'updated_at']
    
    inlines = [
        CallActivityInline, MeetingActivityInline, EmailActivityInline,
        ProposalActivityInline, TaskActivityInline, ActivityLogInline
    ]
    
    def is_overdue_display(self, obj):
        if obj.is_overdue:
            return format_html('<span class="text-danger"><i class="fas fa-exclamation-triangle"></i> Overdue</span>')
        return '✓'
    is_overdue_display.short_description = 'Status'
    
    def reviewed_display(self, obj):
        if obj.reviewed_by_supervisor:
            return format_html('<span class="text-success"><i class="fas fa-check"></i> Reviewed</span>')
        return format_html('<span class="text-warning"><i class="fas fa-clock"></i> Pending</span>')
    reviewed_display.short_description = 'Supervisor Review'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # If user is a supervisor, only show activities from their team
        if request.user.role == 'supervisor':
            qs = qs.filter(salesperson__team_membership__group__supervisor=request.user)
        elif request.user.role == 'salesperson':
            qs = qs.filter(salesperson=request.user)
        return qs

@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['activity', 'action', 'changed_by', 'timestamp']
    list_filter = ['action', 'timestamp']
    search_fields = ['activity__title', 'description', 'changed_by__username']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'

@admin.register(SupervisorReport)
class SupervisorReportAdmin(admin.ModelAdmin):
    list_display = [
        'report_type', 'supervisor', 'group', 'period_start', 'period_end',
        'total_activities', 'completed_activities', 'completion_rate_display'
    ]
    list_filter = ['report_type', 'supervisor', 'group']
    date_hierarchy = 'created_at'
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Report Information', {
            'fields': ('supervisor', 'group', 'report_type')
        }),
        ('Period', {
            'fields': ('period_start', 'period_end')
        }),
        ('Metrics', {
            'fields': (
                'total_activities', 'completed_activities', 'calls_made',
                'meetings_held', 'emails_sent', 'proposals_sent', 'tasks_completed'
            )
        }),
        ('Performance', {
            'fields': ('average_activity_completion_rate', 'team_productivity_score')
        }),
        ('Notes', {
            'fields': ('notes',)
        })
    )
    
    def completion_rate_display(self, obj):
        rate = (obj.completed_activities / obj.total_activities * 100) if obj.total_activities > 0 else 0
        color = 'success' if rate >= 80 else 'warning' if rate >= 60 else 'danger'
        return format_html('<span class="text-{}">{:.1f}%</span>', color, rate)
    completion_rate_display.short_description = 'Completion Rate'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Supervisors can only see their own reports
        if request.user.role == 'supervisor':
            qs = qs.filter(supervisor=request.user)
        return qs

@admin.register(ActivityReminder)
class ActivityReminderAdmin(admin.ModelAdmin):
    list_display = ['activity', 'reminder_type', 'recipient', 'is_sent', 'is_read', 'created_at']
    list_filter = ['reminder_type', 'is_sent', 'is_read', 'created_at']
    search_fields = ['activity__title', 'recipient__username', 'message']
    readonly_fields = ['sent_at', 'read_at']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Users can only see their own reminders
        if not request.user.is_superuser:
            qs = qs.filter(recipient=request.user)
        return qs


@admin.register(FiscalYearSummary)
class FiscalYearSummaryAdmin(admin.ModelAdmin):
    """Frozen year-end snapshots. Read-only — generated by the snapshot command."""
    list_display = [
        'fiscal_year', 'scope_type', 'scope_name', 'won_count', 'lost_count',
        'win_rate', 'total_profit', 'quota', 'generated_at'
    ]
    list_filter = ['fiscal_year', 'scope_type']
    search_fields = ['scope_name']
    readonly_fields = [
        'fiscal_year', 'scope_type', 'scope_id', 'scope_name', 'won_count',
        'lost_count', 'win_rate', 'total_revenue', 'total_profit', 'avg_deal_size',
        'monthly_profit', 'quota', 'generated_at', 'generated_by', 'notes'
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(FiscalYearSnapshotLog)
class FiscalYearSnapshotLogAdmin(admin.ModelAdmin):
    list_display = ['fiscal_year', 'action', 'scope_rows', 'performed_by', 'performed_at']
    list_filter = ['fiscal_year', 'action']
    readonly_fields = ['fiscal_year', 'action', 'scope_rows', 'performed_by', 'performed_at', 'notes']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
