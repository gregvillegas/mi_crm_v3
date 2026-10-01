from decimal import Decimal
from django.db import models
from users.models import User

class Team(models.Model):
    name = models.CharField(max_length=100, unique=True)
    avp = models.ForeignKey(User, on_delete=models.CASCADE, related_name='managed_teams', blank=True, null=True, limit_choices_to={'role__in': ['avp', 'vp', 'gm', 'president']})
    asm = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='asm_teams', blank=True, null=True, limit_choices_to={'role': 'asm'})
    tech_manager = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='tsg_managed_teams', blank=True, null=True, limit_choices_to={'role__in': ['techmgr', 'asst_techmgr']})

    def __str__(self):
        return self.name
    
    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.avp and not self.tech_manager:
            raise ValidationError("A team must have either an AVP or a Technical Manager assigned.")

class Group(models.Model):
    # Group type choices
    GROUP_TYPE_CHOICES = [
        ('regular', 'Regular Sales Group'),
        ('tsg', 'Technical Sales Group'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='groups')
    
    # Group type field
    group_type = models.CharField(max_length=20, choices=GROUP_TYPE_CHOICES, default='regular',
                              help_text='Regular groups have supervisors; TSG groups are managed by the Technical Manager/Assistant Technical Manager')
    
    # Supervisor field for regular groups (can be null for TSG groups)
    supervisor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='managed_groups', 
                                limit_choices_to={'role__in': ['supervisor', 'asm']},
                                null=True, blank=True,
                                help_text='Required for regular groups, not used for TSG groups')
    
    # Sales Managers assigned to oversee this group (subset of a team's groups).
    # Both 'sm' and 'asm' roles display as "Sales Manager" and can be scoped to
    # specific groups here. This lets an ASM oversee only their assigned groups
    # instead of the whole team.
    sm_managers = models.ManyToManyField(
        User,
        related_name='sm_groups',
        blank=True,
        limit_choices_to={'role__in': ['sm', 'asm']},
        help_text='Sales Managers (SM/ASM) responsible for this group. One manager can oversee multiple groups within a team.',
    )

    # Whether this group requires SM/ASM approval in the proposal approval chain.
    # If False: approval goes Supervisor → AVP (2 levels)
    # If True: approval goes Supervisor → SM → AVP (3 levels)
    requires_sm_approval = models.BooleanField(
        default=False,
        help_text='If checked, proposals from this group require SM approval before AVP.',
    )

    # Teamlead stays the same for all group types
    teamlead = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='led_groups', 
                             blank=True, null=True, limit_choices_to={'role': 'teamlead'})

    def __str__(self):
        if self.group_type == 'tsg':
            return f"{self.name} [TSG - {self.team.name}]"
        return f"{self.name} ({self.team.name})"
        
    def get_manager(self):
        """Return the manager of this group - supervisor (regular) or Technical Manager (TSG)"""
        if self.group_type == 'tsg':
            return self.team.tech_manager  # TSG groups managed by the team's Technical Manager
        return self.supervisor  # Regular groups managed by supervisor
        
    def get_manager_role(self):
        """Return the role title of the manager"""
        if self.group_type == 'tsg':
            if self.team.tech_manager:
                return 'Assistant Technical Manager' if self.team.tech_manager.role == 'asst_techmgr' else 'Technical Manager'
            return 'Technical Manager'
        elif self.supervisor and self.supervisor.role == 'asm':
            return 'ASM (Acting Supervisor)'  # ASM acting as supervisor
        return 'Supervisor'  # Regular groups managed by supervisor
        
    def is_tsg(self):
        """Check if this is a Technical Sales Group"""
        return self.group_type == 'tsg'
        
    def clean(self):
        """Validate the group configuration"""
        from django.core.exceptions import ValidationError
        
        if self.group_type == 'tsg':
            # TSG groups should not have a supervisor
            if self.supervisor:
                raise ValidationError("TSG groups are managed by AVPs, not supervisors. Leave supervisor field empty.")
        else:
            # Regular groups must have a supervisor
            if not self.supervisor:
                raise ValidationError("Regular groups must have a supervisor assigned.")
        
    def save(self, *args, **kwargs):
        self.clean()  # Validate before saving
        super().save(*args, **kwargs)
        
    class Meta:
        ordering = ['team__name', 'group_type', 'name']

class TeamMembership(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='team_membership')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='members')
    quota = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Sales quota for this user in this group (Profit based)"
    )

    def __str__(self):
        return f"{self.user.username} in {self.group.name}"

class SupervisorCommitment(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='supervisor_commitments')
    supervisor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='monthly_commitments',
        limit_choices_to={'role__in': ['supervisor', 'asm']}
    )
    month = models.DateField()
    target_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.supervisor.username} {self.month.strftime('%Y-%m')} {self.group.name}"

    class Meta:
        unique_together = ('group', 'month')
        ordering = ['-month']

class SupervisorCommitmentLog(models.Model):
    CHANGE_CHOICES = [
        ('increase', 'Increase'),
        ('decrease', 'Decrease'),
        ('no_change', 'No Change'),
    ]
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='commitment_logs')
    supervisor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='commitment_logs')
    month = models.DateField()
    previous_target = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    new_target = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    change_type = models.CharField(max_length=20, choices=CHANGE_CHOICES)
    changed_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='commitment_changes')
    changed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.group.name} {self.month.strftime('%Y-%m')} {self.change_type} {self.previous_target}->{self.new_target}"

    class Meta:
        ordering = ['-changed_at']

class PersonalContribution(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='personal_contributions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='personal_contributions', limit_choices_to={'role__in': ['avp', 'asm']})
    month = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} {self.group.name} {self.month.strftime('%Y-%m')} ₱{self.amount}"

    class Meta:
        unique_together = ('group', 'user', 'month')
        ordering = ['-month']

class AsmPersonalTarget(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='asm_targets')
    asm = models.ForeignKey(User, on_delete=models.CASCADE, related_name='asm_team_targets', limit_choices_to={'role': 'asm'})
    month = models.DateField()
    target_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.team.name} ASM {self.asm.username} {self.month.strftime('%Y-%m')} ₱{self.target_amount}"
    
    class Meta:
        unique_together = ('team', 'asm', 'month')
        ordering = ['-month']

class RoleMonthlyQuota(models.Model):
    # Default monthly quota (PHP) applied to supervisor/ASM/AVP roles when no
    # explicit quota has been set for the month. Still fully editable per user
    # per month via the "Edit Quota" action on the Executive Dashboard.
    DEFAULT_AMOUNT = Decimal('200000.00')

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='role_monthly_quotas', limit_choices_to={'role__in': ['supervisor', 'asm', 'avp', 'gm', 'vp']})
    month = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=DEFAULT_AMOUNT)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'month')
        ordering = ['-month']

    def __str__(self):
        return f"{self.user.username} {self.month.strftime('%Y-%m')} ₱{self.amount}"

class CompanyAnnualTarget(models.Model):
    year = models.IntegerField()
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    set_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, limit_choices_to={'role__in': ['gm', 'vp', 'admin']}, related_name='company_targets_set')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('year',)
        ordering = ['-year']
    
    def __str__(self):
        return f"Company Annual Target {self.year} ₱{self.amount}"

class CompanyAnnualTargetLog(models.Model):
    target = models.ForeignKey(CompanyAnnualTarget, on_delete=models.CASCADE, related_name='change_logs')
    previous_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    new_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='company_target_changes')
    changed_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-changed_at']
    
    def __str__(self):
        return f"{self.target.year} change: ₱{self.previous_amount} → ₱{self.new_amount}"


def asm_scoped_groups(user):
    """
    Return the set of Groups an ASM should be scoped to (Option A behavior).

    - If the ASM is explicitly assigned to specific groups via Group.sm_managers
      (reverse accessor ``user.sm_groups``), return ONLY those groups.
    - Otherwise (no explicit assignments), fall back to ALL groups in the ASM's
      team(s) (``user.asm_teams``) — this preserves legacy behavior for ASMs who
      genuinely oversee an entire team.

    This lets an ASM (whose job title is "Sales Manager") be restricted to just
    the groups they handle, while never accidentally hiding data for an ASM who
    has not been assigned to specific groups yet.
    """
    assigned = user.sm_groups.all()
    if assigned.exists():
        return assigned
    return Group.objects.filter(team__in=user.asm_teams.all())
