from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import Team, Group, TeamMembership, SupervisorCommitment, asm_scoped_groups
from .forms import TeamForm, GroupForm, GroupEditForm, TeamMembershipQuotaForm, SupervisorCommitmentForm, PersonalContributionForm, AsmPersonalTargetForm, RoleMonthlyQuotaForm
from users.models import User
from django.contrib.auth.decorators import user_passes_test, login_required
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages

def is_admin(user):
    return user.role == 'admin'

def can_view_teams(user):
    return user.role in ['admin', 'president', 'gm', 'vp', 'avp', 'asm', 'sm', 'supervisor', 'techmgr', 'asst_techmgr']

def can_manage_teams(user):
    return user.role in ['admin', 'president', 'gm', 'vp']

def can_manage_groups(user):
    return user.role in ['admin', 'president', 'gm', 'vp', 'avp', 'asm', 'sm', 'supervisor', 'techmgr', 'asst_techmgr']

@login_required
@user_passes_test(can_view_teams)
def team_list(request):
    if request.user.role == 'asm':
        # Show only teams that contain at least one of the ASM's scoped groups.
        teams = Team.objects.filter(groups__in=asm_scoped_groups(request.user)).distinct()
    elif request.user.role == 'sm':
        # SM sees only teams that contain at least one of their assigned groups
        teams = Team.objects.filter(groups__in=request.user.sm_groups.all()).distinct()
    elif request.user.role in ['techmgr', 'asst_techmgr']:
        teams = Team.objects.filter(tech_manager=request.user)
    else:
        teams = Team.objects.all()
    return render(request, 'teams/team_list.html', {'teams': teams})

@login_required
@user_passes_test(can_manage_teams)
def create_team(request):
    if request.method == 'POST':
        form = TeamForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('team_list')
    else:
        form = TeamForm()
    return render(request, 'teams/team_form.html', {'form': form, 'title': 'Create Team'})

@login_required
@user_passes_test(can_view_teams)
def team_groups(request, pk):
    team = get_object_or_404(Team, pk=pk)
    if request.user.role == 'asm':
        # ASM can only view a team that contains at least one of their scoped groups
        if not asm_scoped_groups(request.user).filter(team=team).exists():
            from django.http import Http404
            raise Http404("You don't have permission to view this team.")
    if request.user.role == 'sm':
        # SM can only view a team if they manage at least one group within it
        if not request.user.sm_groups.filter(team=team).exists():
            from django.http import Http404
            raise Http404("You don't have permission to view this team.")
    groups = Group.objects.filter(team=team)
    # ASM sees only their scoped groups within that team
    if request.user.role == 'asm':
        groups = groups.filter(pk__in=asm_scoped_groups(request.user).values_list('pk', flat=True))
    # SM sees only their assigned groups within that team
    if request.user.role == 'sm':
        groups = groups.filter(sm_managers=request.user)
    return render(request, 'teams/team_groups.html', {'team': team, 'groups': groups})

@login_required
@user_passes_test(can_manage_groups)
def group_list(request):
    if request.user.role in ['admin', 'president', 'gm', 'vp']:
        groups = Group.objects.all()
    elif request.user.role == 'avp':
        user_teams = Team.objects.filter(avp=request.user)
        groups = Group.objects.filter(team__in=user_teams)
    elif request.user.role == 'asm':
        groups = asm_scoped_groups(request.user)
    elif request.user.role == 'sm':
        groups = request.user.sm_groups.all()
    elif request.user.role in ['techmgr', 'asst_techmgr']:
        user_teams = Team.objects.filter(tech_manager=request.user)
        groups = Group.objects.filter(team__in=user_teams)
    elif request.user.role == 'supervisor':
        groups = request.user.managed_groups.all()
    else:
        groups = Group.objects.all()
    return render(request, 'teams/group_list.html', {'groups': groups})

@login_required
@user_passes_test(can_manage_groups)
def create_group(request):
    if request.method == 'POST':
        form = GroupForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('group_list')
    else:
        form = GroupForm()
    return render(request, 'teams/group_form.html', {'form': form, 'title': 'Create Group'})

@login_required
@user_passes_test(can_view_teams)
def group_members(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if request.user.role == 'asm':
        if not asm_scoped_groups(request.user).filter(pk=group.pk).exists():
            from django.http import Http404
            raise Http404("You don't have permission to view this group.")
    elif request.user.role == 'sm':
        if not request.user.sm_groups.filter(pk=group.pk).exists():
            from django.http import Http404
            raise Http404("You don't have permission to view this group.")
    elif request.user.role == 'avp':
        user_teams = Team.objects.filter(avp=request.user)
        if group.team not in user_teams:
            from django.http import Http404
            raise Http404("You don't have permission to view this group.")
    elif request.user.role in ['techmgr', 'asst_techmgr']:
        user_teams = Team.objects.filter(tech_manager=request.user)
        if group.team not in user_teams:
            from django.http import Http404
            raise Http404("You don't have permission to view this group.")
    elif request.user.role == 'supervisor':
        if group.supervisor != request.user:
            from django.http import Http404
            raise Http404("You don't have permission to view this group.")
    members = User.objects.filter(team_membership__group=group)
    can_edit = False
    if request.user.role == 'asm':
        can_edit = asm_scoped_groups(request.user).filter(pk=group.pk).exists()
    elif request.user.role == 'sm':
        can_edit = request.user.sm_groups.filter(pk=group.pk).exists()
    elif request.user.role == 'avp':
        user_teams = Team.objects.filter(avp=request.user)
        can_edit = group.team in user_teams
    elif request.user.role in ['techmgr', 'asst_techmgr']:
        user_teams = Team.objects.filter(tech_manager=request.user)
        can_edit = group.team in user_teams
    elif request.user.role == 'supervisor':
        can_edit = group.supervisor == request.user
    return render(request, 'teams/group_members.html', {'group': group, 'members': members, 'can_edit': can_edit})

@login_required
@user_passes_test(can_manage_groups)
def edit_group(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if request.user.role == 'asm':
        if not asm_scoped_groups(request.user).filter(pk=group.pk).exists():
            from django.http import Http404
            raise Http404("You don't have permission to edit this group.")
    elif request.user.role == 'sm':
        if not request.user.sm_groups.filter(pk=group.pk).exists():
            from django.http import Http404
            raise Http404("You don't have permission to edit this group.")
    elif request.user.role == 'avp':
        user_teams = Team.objects.filter(avp=request.user)
        if group.team not in user_teams:
            from django.http import Http404
            raise Http404("You don't have permission to edit this group.")
    elif request.user.role in ['techmgr', 'asst_techmgr']:
        user_teams = Team.objects.filter(tech_manager=request.user)
        if group.team not in user_teams:
            from django.http import Http404
            raise Http404("You don't have permission to edit this group.")
    elif request.user.role == 'supervisor':
        if group.supervisor != request.user:
            from django.http import Http404
            raise Http404("You don't have permission to edit this group.")
    if request.method == 'POST':
        form = GroupEditForm(request.POST, instance=group)
        if form.is_valid():
            form.save()
            return redirect('group_members', pk=group.pk)
    else:
        form = GroupEditForm(instance=group)
    return render(request, 'teams/group_edit.html', {'form': form, 'group': group, 'title': f'Edit {group.name}'})

@login_required
@user_passes_test(can_manage_groups)
def update_member_quota(request, pk):
    membership = get_object_or_404(TeamMembership, pk=pk)
    group = membership.group
    if request.user.role == 'asm':
        if not asm_scoped_groups(request.user).filter(pk=group.pk).exists():
            from django.http import Http404
            raise Http404("You don't have permission to edit members of this group.")
    elif request.user.role == 'sm':
        if not request.user.sm_groups.filter(pk=group.pk).exists():
            from django.http import Http404
            raise Http404("You don't have permission to edit members of this group.")
    elif request.user.role == 'avp':
        user_teams = Team.objects.filter(avp=request.user)
        if group.team not in user_teams:
            from django.http import Http404
            raise Http404("You don't have permission to edit members of this group.")
    elif request.user.role == 'supervisor':
        if group.supervisor != request.user:
            from django.http import Http404
            raise Http404("You don't have permission to edit members of this group.")
    if request.method == 'POST':
        form = TeamMembershipQuotaForm(request.POST, instance=membership)
        if form.is_valid():
            form.save()
            return redirect('group_members', pk=group.pk)
    else:
        form = TeamMembershipQuotaForm(instance=membership)
    return render(request, 'teams/update_quota.html', {'form': form, 'membership': membership, 'group': group, 'title': f'Update Quota - {membership.user.get_full_name() or membership.user.username}'})

@login_required
@user_passes_test(can_manage_groups)
def update_supervisor_commitment(request, pk):
    group = get_object_or_404(Group, pk=pk)
    # Scope enforcement: AVP can update only within her teams; exec/admin can update all; supervisor/asm/sm can update own groups
    if request.user.role == 'avp':
        if group.team.avp != request.user:
            from django.http import Http404
            raise Http404("You don't have permission to edit this group's commitment.")
    elif request.user.role == 'asm':
        if not asm_scoped_groups(request.user).filter(pk=group.pk).exists():
            from django.http import Http404
            raise Http404("You don't have permission to edit this group's commitment.")
    elif request.user.role == 'sm':
        if not request.user.sm_groups.filter(pk=group.pk).exists():
            from django.http import Http404
            raise Http404("You don't have permission to edit this group's commitment.")
    elif request.user.role == 'supervisor':
        if group.supervisor != request.user:
            from django.http import Http404
            raise Http404("You don't have permission to edit this group's commitment.")

    today = timezone.now().date()
    month_start = today.replace(day=1)
    supervisor = group.supervisor
    commitment, _ = SupervisorCommitment.objects.get_or_create(
        group=group,
        supervisor=supervisor,
        month=month_start,
        defaults={'target_profit': 0}
    )
    if request.method == 'POST':
        form = SupervisorCommitmentForm(request.POST, instance=commitment)
        if form.is_valid():
            prev = commitment.target_profit
            inst = form.save()
            from .models import SupervisorCommitmentLog
            change_type = 'no_change'
            try:
                if inst.target_profit > prev:
                    change_type = 'increase'
                elif inst.target_profit < prev:
                    change_type = 'decrease'
            except Exception:
                change_type = 'no_change'
            SupervisorCommitmentLog.objects.create(
                group=group,
                supervisor=supervisor,
                month=month_start,
                previous_target=prev or 0,
                new_target=inst.target_profit or 0,
                change_type=change_type,
                changed_by=request.user
            )
            from django.contrib import messages
            messages.success(request, 'Supervisor commitment updated.')
            return redirect('sales_monitoring:dashboard')
    else:
        form = SupervisorCommitmentForm(instance=commitment)
    return render(request, 'teams/update_commitment.html', {'form': form, 'group': group, 'title': f'Update Commitment - {group.name}'})

@login_required
@user_passes_test(can_view_teams)
def commitment_history(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if request.user.role == 'avp':
        user_teams = Team.objects.filter(avp=request.user)
        if group.team not in user_teams:
            from django.http import Http404
            raise Http404("You don't have permission to view this history.")
    elif request.user.role == 'asm':
        if not asm_scoped_groups(request.user).filter(pk=group.pk).exists():
            from django.http import Http404
            raise Http404("You don't have permission to view this history.")
    elif request.user.role == 'sm':
        if not request.user.sm_groups.filter(pk=group.pk).exists():
            from django.http import Http404
            raise Http404("You don't have permission to view this history.")
    elif request.user.role == 'supervisor':
        if group.supervisor != request.user:
            from django.http import Http404
            raise Http404("You don't have permission to view this history.")
    from .models import SupervisorCommitmentLog
    logs = SupervisorCommitmentLog.objects.filter(group=group).order_by('-changed_at')
    return render(request, 'teams/commitment_history.html', {'group': group, 'logs': logs, 'title': f'Commitment History - {group.name}'})

@login_required
@user_passes_test(can_manage_groups)
def update_personal_contribution(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if request.user.role == 'avp':
        if group.team.avp != request.user:
            from django.http import Http404
            raise Http404("You don't have permission to edit this contribution.")
    elif request.user.role == 'asm':
        if not asm_scoped_groups(request.user).filter(pk=group.pk).exists():
            from django.http import Http404
            raise Http404("You don't have permission to edit this contribution.")
    elif request.user.role == 'sm':
        if not request.user.sm_groups.filter(pk=group.pk).exists():
            from django.http import Http404
            raise Http404("You don't have permission to edit this contribution.")
    today = timezone.now().date()
    month_start = today.replace(day=1)
    from .models import PersonalContribution
    contrib, _ = PersonalContribution.objects.get_or_create(
        group=group,
        user=request.user,
        month=month_start,
        defaults={'amount': 0}
    )
    if request.method == 'POST':
        form = PersonalContributionForm(request.POST, instance=contrib)
        if form.is_valid():
            form.save()
            from django.contrib import messages
            messages.success(request, 'Personal contribution updated.')
            return redirect('sales_monitoring:dashboard')
    else:
        form = PersonalContributionForm(instance=contrib)
    return render(request, 'teams/update_contribution.html', {'form': form, 'group': group, 'title': f'Update Contribution - {group.name}'})

@login_required
@user_passes_test(can_manage_groups)
def update_asm_target(request, pk):
    team = get_object_or_404(Team, pk=pk)
    if request.user.role == 'avp':
        if team.avp != request.user:
            from django.http import Http404
            raise Http404("You don't have permission to edit this ASM target.")
    today = timezone.now().date()
    month_start = today.replace(day=1)
    asm = team.asm
    if not asm:
        from django.contrib import messages
        messages.error(request, 'This team does not have an ASM assigned.')
        return redirect('sales_monitoring:dashboard')
    from .models import AsmPersonalTarget
    target, _ = AsmPersonalTarget.objects.get_or_create(
        team=team,
        asm=asm,
        month=month_start,
        defaults={'target_amount': 0}
    )
    if request.method == 'POST':
        form = AsmPersonalTargetForm(request.POST, instance=target)
        if form.is_valid():
            form.save()
            from django.contrib import messages
            messages.success(request, 'ASM personal sales target updated.')
            return redirect('sales_monitoring:executive_dashboard') if request.user.role in ['vp','gm','president','admin'] else redirect('sales_monitoring:dashboard')
    else:
        form = AsmPersonalTargetForm(instance=target)
    return render(request, 'teams/update_asm_target.html', {'form': form, 'team': team, 'title': f'Update ASM Target - {team.name}'})

@login_required
@user_passes_test(can_manage_groups)
def update_role_quota(request, user_id):
    target_user = get_object_or_404(User, pk=user_id, role__in=['supervisor','asm','avp'])
    # Scope: AVP can edit quotas for supervisors/ASM within her teams and her own AVP quota; Admin/executive can edit all
    if request.user.role == 'avp':
        allowed = False
        from .models import Team, Group
        teams = Team.objects.filter(avp=request.user)
        if target_user.role == 'avp' and target_user == request.user:
            allowed = True
        elif target_user.role == 'asm' and teams.filter(asm=target_user).exists():
            allowed = True
        elif target_user.role == 'supervisor' and Group.objects.filter(team__in=teams, supervisor=target_user).exists():
            allowed = True
        if not allowed:
            from django.http import Http404
            raise Http404("You don't have permission to edit this quota.")
    today = timezone.now().date()
    month_start = today.replace(day=1)
    from .models import RoleMonthlyQuota
    quota, _ = RoleMonthlyQuota.objects.get_or_create(
        user=target_user, month=month_start,
        defaults={'amount': RoleMonthlyQuota.DEFAULT_AMOUNT},
    )
    if request.method == 'POST':
        form = RoleMonthlyQuotaForm(request.POST, instance=quota)
        if form.is_valid():
            form.save()
            from django.contrib import messages
            messages.success(request, 'Monthly quota updated.')
            return redirect('sales_monitoring:dashboard')
    else:
        form = RoleMonthlyQuotaForm(instance=quota)
    return render(request, 'teams/update_role_quota.html', {'form': form, 'target_user': target_user, 'title': f'Update Quota - {target_user.get_full_name() or target_user.username}'})

def can_manage_company_target(user):
    return user.role in ['gm', 'vp', 'admin']

@login_required
@user_passes_test(can_manage_company_target)
def update_company_target(request):
    from .models import CompanyAnnualTarget, CompanyAnnualTargetLog
    from .forms import CompanyAnnualTargetForm
    today = timezone.now().date()
    current_year = today.year
    target = CompanyAnnualTarget.objects.filter(year=current_year).first()
    if request.method == 'POST':
        form = CompanyAnnualTargetForm(request.POST, instance=target)
        if form.is_valid():
            previous_amount = target.amount if target else 0
            instance = form.save(commit=False)
            if not instance.pk:
                instance.set_by = request.user
            instance.save()
            CompanyAnnualTargetLog.objects.create(
                target=instance,
                previous_amount=previous_amount,
                new_amount=instance.amount,
                changed_by=request.user,
                notes=f"Updated by {request.user.get_full_name() or request.user.username}"
            )
            messages.success(request, 'Company annual target updated.')
            return redirect('sales_monitoring:executive_dashboard')
    else:
        if target:
            form = CompanyAnnualTargetForm(instance=target)
        else:
            form = CompanyAnnualTargetForm(initial={'year': current_year})
    logs = CompanyAnnualTargetLog.objects.filter(target__year=current_year)[:10]
    return render(request, 'teams/update_company_target.html', {'form': form, 'logs': logs, 'title': f'Update Company Annual Target ({current_year})'})

@login_required
def quota_management(request):
    if request.user.role != 'avp':
         from django.http import HttpResponseForbidden
         return HttpResponseForbidden("You don't have permission to access this page.")
    
    from .models import RoleMonthlyQuota
    
    # Get AVP's Teams
    teams = Team.objects.filter(avp=request.user)
    
    today = timezone.now().date()
    month_start = today.replace(day=1)
    
    team_data = []
    for team in teams:
        asm_quota = None
        if team.asm:
             asm_quota = RoleMonthlyQuota.objects.filter(user=team.asm, month=month_start).first()
        
        groups = Group.objects.filter(team=team)
        group_data = []
        for group in groups:
            supervisor_quota = None
            if group.supervisor:
                supervisor_quota = RoleMonthlyQuota.objects.filter(user=group.supervisor, month=month_start).first()
            
            memberships = TeamMembership.objects.filter(group=group)
            
            group_data.append({
                'group': group,
                'supervisor_quota': supervisor_quota,
                'memberships': memberships
            })
            
        team_data.append({
            'team': team,
            'asm_quota': asm_quota,
            'groups': group_data
        })
    
    # Also get AVP's own quota
    avp_quota = RoleMonthlyQuota.objects.filter(user=request.user, month=month_start).first()

    return render(request, 'teams/quota_management.html', {
        'team_data': team_data, 
        'month': month_start,
        'avp_quota': avp_quota
    })
