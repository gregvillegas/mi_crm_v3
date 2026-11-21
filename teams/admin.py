from django.contrib import admin
from .models import Team, Group, TeamMembership, TeamMembershipQuotaLog, SupervisorCommitment, SupervisorCommitmentLog, PersonalContribution, AsmPersonalTarget, RoleMonthlyQuota, CompanyAnnualTarget, CompanyAnnualTargetLog


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'avp', 'asm', 'tech_manager')
    list_filter = ('avp', 'tech_manager')
    search_fields = ('name', 'avp__username', 'avp__first_name', 'avp__last_name', 'tech_manager__username', 'tech_manager__first_name', 'tech_manager__last_name')
    

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'team', 'group_type', 'get_manager_display', 'teamlead')
    list_filter = ('group_type', 'team')
    search_fields = ('name', 'team__name')
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'team', 'group_type')
        }),
        ('Management', {
            'fields': ('supervisor', 'teamlead'),
            'description': 'For TSG groups, leave supervisor empty - they are managed by the team Technical Manager.'
        }),
        ('Approval Settings', {
            'fields': ('requires_sm_approval',),
            'description': 'Controls whether proposals from this group require SM approval before AVP.'
        }),
    )
    
    def get_manager_display(self, obj):
        """Display the manager with their role"""
        manager = obj.get_manager()
        if manager:
            return f"{manager.get_full_name()} ({obj.get_manager_role()})"
        return "No manager assigned"
    get_manager_display.short_description = 'Manager'
    get_manager_display.admin_order_field = 'supervisor'
    
    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        
        # Add help text and dynamic field behavior based on group_type
        if 'group_type' in form.base_fields:
            form.base_fields['group_type'].help_text = (
                'Regular groups are managed by supervisors. '
                'TSG (Technical Sales Groups) are managed directly by the team AVP.'
            )
        
        return form
        
    class Media:
        js = ('admin/js/tsg_group_admin.js',)  # We'll create this for dynamic form behavior


@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'group', 'get_group_type', 'get_manager')
    list_filter = ('group__group_type', 'group__team')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'group__name')
    
    def get_group_type(self, obj):
        return obj.group.get_group_type_display()
    get_group_type.short_description = 'Group Type'
    get_group_type.admin_order_field = 'group__group_type'
    
    def get_manager(self, obj):
        manager = obj.group.get_manager()
        return f"{manager.get_full_name()} ({obj.group.get_manager_role()})" if manager else "No manager"
    get_manager.short_description = 'Managed By'
    get_manager.admin_order_field = 'group__supervisor'

@admin.register(TeamMembershipQuotaLog)
class TeamMembershipQuotaLogAdmin(admin.ModelAdmin):
    list_display = ('team_membership', 'previous_quota', 'new_quota', 'change_type', 'changed_by', 'changed_at')
    list_filter = ('change_type',)
    search_fields = ('team_membership__user__username', 'team_membership__user__first_name', 'team_membership__user__last_name', 'changed_by__username')
    readonly_fields = ('team_membership', 'previous_quota', 'new_quota', 'change_type', 'changed_by', 'changed_at')

@admin.register(SupervisorCommitment)
class SupervisorCommitmentAdmin(admin.ModelAdmin):
    list_display = ('group', 'supervisor', 'month', 'target_profit')
    list_filter = ('group__team', 'month')
    search_fields = ('group__name', 'supervisor__username', 'supervisor__first_name', 'supervisor__last_name')

@admin.register(SupervisorCommitmentLog)
class SupervisorCommitmentLogAdmin(admin.ModelAdmin):
    list_display = ('group', 'supervisor', 'month', 'previous_target', 'new_target', 'change_type', 'changed_by', 'changed_at')
    list_filter = ('group__team', 'month', 'change_type')
    search_fields = ('group__name', 'supervisor__username', 'changed_by__username')

@admin.register(PersonalContribution)
class PersonalContributionAdmin(admin.ModelAdmin):
    list_display = ('group', 'user', 'month', 'amount')
    list_filter = ('group__team', 'month')
    search_fields = ('group__name', 'user__username', 'user__first_name', 'user__last_name')

@admin.register(AsmPersonalTarget)
class AsmPersonalTargetAdmin(admin.ModelAdmin):
    list_display = ('team', 'asm', 'month', 'target_amount')
    list_filter = ('team', 'month')
    search_fields = ('team__name', 'asm__username', 'asm__first_name', 'asm__last_name')

@admin.register(RoleMonthlyQuota)
class RoleMonthlyQuotaAdmin(admin.ModelAdmin):
    list_display = ('user', 'month', 'amount')
    list_filter = ('user__role', 'month')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')

@admin.register(CompanyAnnualTarget)
class CompanyAnnualTargetAdmin(admin.ModelAdmin):
    list_display = ('year', 'amount', 'set_by', 'updated_at')
    list_filter = ('year',)
    search_fields = ('set_by__username',)

@admin.register(CompanyAnnualTargetLog)
class CompanyAnnualTargetLogAdmin(admin.ModelAdmin):
    list_display = ('target', 'previous_amount', 'new_amount', 'changed_by', 'changed_at')
    list_filter = ('target__year',)
    search_fields = ('changed_by__username',)
