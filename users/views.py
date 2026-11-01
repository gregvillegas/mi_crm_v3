from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.core.management import call_command
from django.db.models import Q
from .forms import SalespersonCreationForm, UserProfileForm
from .models import User, UserActivityLog
from teams.models import TeamMembership, Group
import tempfile
import os
import json
from datetime import datetime

# ... existing code ...

@login_required
def profile_view(request):
    """Allow users to view and update their own profile"""
    user = request.user
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            # Check for changes to log
            if form.has_changed():
                changes = {}
                for field in form.changed_data:
                    changes[field] = {
                        'old': form.initial.get(field),
                        'new': form.cleaned_data.get(field)
                    }
                
                # Save changes
                form.save()
                
                # Log the activity
                UserActivityLog.objects.create(
                    user=user,
                    path=request.path,
                    method='POST',
                    ip_address=request.META.get('REMOTE_ADDR'),
                    details=f"User updated profile. Changes: {json.dumps(changes, default=str)}"
                )
                
                messages.success(request, 'Your profile has been updated successfully.')
                return redirect('profile')
    else:
        form = UserProfileForm(instance=user)
    
    # Check if user has MFA enabled
    has_totp = False
    try:
        from allauth.mfa.models import Authenticator
        has_totp = Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists()
    except Exception:
        pass  # allauth.mfa might not be fully set up yet
    
    return render(request, 'users/profile.html', {
        'form': form,
        'has_totp': has_totp,
    })


def is_manager(user):
    return user.role in ['admin', 'vp', 'avp', 'supervisor', 'asm', 'teamlead']

def is_admin(user):
    return user.role in ['admin', 'vp']

def is_executive(user):
    return user.role in ['admin', 'president', 'gm', 'vp']

def can_view_teams(user):
    return user.role in ['admin', 'president', 'gm', 'vp', 'avp', 'asm']

def can_manage_groups(user):
    return user.role in ['admin', 'president', 'gm', 'vp', 'avp', 'asm', 'supervisor']

@login_required
@user_passes_test(is_manager)
def create_salesperson(request):
    if request.method == 'POST':
        form = SalespersonCreationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('home') # Or wherever you want to redirect after creation
    else:
        form = SalespersonCreationForm()
    return render(request, 'users/salesperson_form.html', {'form': form})


@login_required
@user_passes_test(is_admin)
def user_management(request):
    """Admin page to manage all users with pagination and search"""
    # Get search query
    search_query = request.GET.get('search', '')
    
    # Start with all users
    users_list = User.objects.all()
    
    # Apply search filter if query exists
    if search_query:
        users_list = users_list.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(initials__icontains=search_query)
        )
    
    # Order users
    users_list = users_list.order_by('role', 'username')
    
    # Pagination
    page_size = request.GET.get('page_size', '20')  # Default to 20 users per page
    try:
        page_size = int(page_size)
        if page_size not in [10, 20, 50, 100]:
            page_size = 20
    except (ValueError, TypeError):
        page_size = 20
    
    paginator = Paginator(users_list, page_size)
    page = request.GET.get('page', 1)
    
    try:
        users = paginator.page(page)
    except PageNotAnInteger:
        users = paginator.page(1)
    except EmptyPage:
        users = paginator.page(paginator.num_pages)
    
    context = {
        'users': users,
        'search_query': search_query,
        'page_size': page_size,
        'total_users': paginator.count,
    }
    
    return render(request, 'users/user_management.html', context)


@login_required
@user_passes_test(is_admin)
def toggle_user_active(request, user_id):
    """Toggle user active status (AJAX endpoint)"""
    if request.method == 'POST':
        try:
            user = get_object_or_404(User, id=user_id)
            
            # Don't allow admin to deactivate themselves
            if user == request.user:
                return JsonResponse({
                    'success': False, 
                    'message': 'You cannot deactivate your own account.'
                })
            
            # Toggle active status
            user.is_active = not user.is_active
            user.save()
            
            action = 'activated' if user.is_active else 'deactivated'
            return JsonResponse({
                'success': True,
                'message': f'User {user.username} has been {action}.',
                'is_active': user.is_active
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'message': 'Invalid request method.'})


@login_required
@user_passes_test(is_admin)
def create_user(request):
    """Create a new user"""
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        mobile_number = request.POST.get('mobile_number')
        initials = request.POST.get('initials', '').upper()  # Convert to uppercase
        role = request.POST.get('role')
        password = request.POST.get('password')
        is_active = request.POST.get('is_active') == 'on'
        handles_all_technical_teams = request.POST.get('handles_all_technical_teams') == 'on'
        ts_approval_exempt = request.POST.get('ts_approval_exempt') == 'on'
        
        # Basic validation
        if not all([username, email, first_name, last_name, role, password]):
            messages.error(request, 'All fields are required.')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
        elif User.objects.filter(email=email).exists():
            messages.error(request, 'Email already exists.')
        else:
            try:
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    mobile_number=mobile_number,
                    initials=initials,
                    role=role,
                    password=password,
                    is_active=is_active,
                    handles_all_technical_teams=handles_all_technical_teams,
                    ts_approval_exempt=ts_approval_exempt,
                )
                messages.success(request, f'User {username} created successfully.')
                return redirect('user_management')
            except Exception as e:
                messages.error(request, f'Error creating user: {str(e)}')
    
    return render(request, 'users/create_user.html', {
        'roles': User.ROLE_CHOICES
    })


@login_required
@user_passes_test(is_admin)
def edit_user(request, user_id):
    """Edit an existing user"""
    user_obj = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        # Get form data
        username = request.POST.get('username')
        email = request.POST.get('email')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        mobile_number = request.POST.get('mobile_number')
        initials = request.POST.get('initials', '').upper()  # Convert to uppercase
        role = request.POST.get('role')
        is_active = request.POST.get('is_active') == 'on'
        handles_all_technical_teams = request.POST.get('handles_all_technical_teams') == 'on'
        ts_approval_exempt = request.POST.get('ts_approval_exempt') == 'on'
        
        # Basic validation
        if not all([username, email, first_name, last_name, role]):
            messages.error(request, 'All fields are required.')
        elif User.objects.filter(username=username).exclude(id=user_id).exists():
            messages.error(request, 'Username already exists.')
        elif User.objects.filter(email=email).exclude(id=user_id).exists():
            messages.error(request, 'Email already exists.')
        else:
            try:
                # Update user fields
                user_obj.username = username
                user_obj.email = email
                user_obj.first_name = first_name
                user_obj.last_name = last_name
                user_obj.mobile_number = mobile_number
                user_obj.initials = initials
                user_obj.role = role
                user_obj.is_active = is_active
                user_obj.handles_all_technical_teams = handles_all_technical_teams
                user_obj.ts_approval_exempt = ts_approval_exempt
                # NOTE: passwords are intentionally NOT set here. Admins reset
                # passwords via the audited "Send Password Reset Link" action so
                # no staff member ever knows a user's password. See send_password_reset.
                user_obj.save()
                messages.success(request, f'User {username} updated successfully.')
                return redirect('user_management')
            except Exception as e:
                messages.error(request, f'Error updating user: {str(e)}')
    
    return render(request, 'users/edit_user.html', {
        'user_obj': user_obj,
        'roles': User.ROLE_CHOICES
    })


@login_required
@user_passes_test(is_manager)
def transfer_salesperson(request, user_id):
    """Transfer a salesperson to another group"""
    salesperson = get_object_or_404(User, id=user_id, role='salesperson')
    
    # Get current team membership
    try:
        current_membership = salesperson.team_membership
    except TeamMembership.DoesNotExist:
        current_membership = None
    
    if request.method == 'POST':
        new_group_id = request.POST.get('new_group')
        
        if not new_group_id:
            messages.error(request, 'Please select a group.')
        else:
            try:
                new_group = get_object_or_404(Group, id=new_group_id)
                
                # Update or create team membership
                if current_membership:
                    current_membership.group = new_group
                    current_membership.save()
                else:
                    TeamMembership.objects.create(
                        user=salesperson,
                        group=new_group
                    )
                
                messages.success(request, f'Salesperson {salesperson.username} has been transferred to {new_group.name}.')
                return redirect('user_management')
                
            except Exception as e:
                messages.error(request, f'Error transferring salesperson: {str(e)}')
    
    # Get all groups for the dropdown
    groups = Group.objects.all().select_related('team')
    
    return render(request, 'users/transfer_salesperson.html', {
        'salesperson': salesperson,
        'current_membership': current_membership,
        'groups': groups
    })


@login_required
@user_passes_test(can_manage_groups)
def assign_teamlead(request, user_id):
    """Assign a teamlead to a group"""
    teamlead = get_object_or_404(User, id=user_id, role='teamlead')
    
    # Get current group assignment
    current_group = Group.objects.filter(teamlead=teamlead).first()
    
    if request.method == 'POST':
        new_group_id = request.POST.get('new_group')
        
        if not new_group_id:
            # Remove teamlead assignment
            if current_group:
                current_group.teamlead = None
                current_group.save()
                messages.success(request, f'Teamlead {teamlead.username} has been unassigned from {current_group.name}.')
            else:
                messages.info(request, f'Teamlead {teamlead.username} was not assigned to any group.')
        else:
            try:
                new_group = get_object_or_404(Group, id=new_group_id)
                
                # Remove from current group if assigned
                if current_group:
                    current_group.teamlead = None
                    current_group.save()
                
                # Assign to new group
                new_group.teamlead = teamlead
                new_group.save()
                
                messages.success(request, f'Teamlead {teamlead.username} has been assigned to {new_group.name}.')
                
            except Exception as e:
                messages.error(request, f'Error assigning teamlead: {str(e)}')
                
        return redirect('user_management')
    
    # Get available groups (filter by user's access if needed)
    if request.user.role == 'asm':
        # ASM can only assign teamleads to groups within their teams
        user_teams = request.user.asm_teams.all()
        groups = Group.objects.filter(team__in=user_teams)
    else:
        groups = Group.objects.all().select_related('team')
    
    return render(request, 'users/assign_teamlead.html', {
        'teamlead': teamlead,
        'current_group': current_group,
        'groups': groups
    })


@login_required
@user_passes_test(is_admin)
def export_users_json(request):
    """Export all users, teams, and relationships to JSON for production deployment"""
    try:
        # Get export options from request
        include_passwords = request.GET.get('include_passwords', 'false').lower() == 'true'
        include_inactive = request.GET.get('include_inactive', 'true').lower() == 'true'
        pretty_print = request.GET.get('pretty', 'true').lower() == 'true'
        
        # Create temporary file for export
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_file:
            temp_file_path = temp_file.name
        
        # Prepare export arguments
        export_args = [
            '--output', temp_file_path,
        ]
        
        if include_passwords:
            export_args.append('--include-passwords')
        
        if include_inactive:
            export_args.append('--include-inactive')
            
        if pretty_print:
            export_args.append('--pretty')
        
        # Run export command
        call_command('export_users', *export_args)
        
        # Read the generated file
        with open(temp_file_path, 'r', encoding='utf-8') as f:
            export_content = f.read()
        
        # Clean up temporary file
        os.unlink(temp_file_path)
        
        # Generate filename for download
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        filename = f'crm_users_export_{timestamp}.json'
        
        # Create HTTP response with file download
        response = HttpResponse(export_content, content_type='application/json')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = len(export_content)
        
        # Add success message for next page load
        messages.success(request, f'User export completed successfully! Downloaded: {filename}')
        
        return response
        
    except Exception as e:
        messages.error(request, f'Export failed: {str(e)}')
        return redirect('user_management')


def is_admin_only(user):
    """Stricter gate for security-sensitive actions (password/MFA resets)."""
    return getattr(user, 'is_authenticated', False) and user.role == 'admin'


@login_required
@user_passes_test(is_admin_only)
def send_password_reset(request, user_id):
    """
    Admin-initiated password reset. Emails the TARGET USER a single-use, time-limited
    reset link (via allauth's own reset flow). The admin never sees or sets the
    password. Audited. POST-only.
    """
    target = get_object_or_404(User, id=user_id)

    if request.method != 'POST':
        return redirect('user_management')

    from .signals import record_reset_audit

    if not target.email:
        messages.error(request, f'{target.username} has no email address on file; cannot send a reset link.')
        record_reset_audit(
            'admin_send_link', request=request, target_user=target,
            target_identifier=target.username, performed_by=request.user,
            notes='FAILED — no email on file.',
        )
        return redirect('user_management')

    sent = False
    try:
        # Reuse allauth's reset form so the token/email are identical to self-service.
        from allauth.account.forms import ResetPasswordForm
        form = ResetPasswordForm({'email': target.email})
        if form.is_valid():
            form.save(request)
            sent = True
        else:
            # Fallback: Django's built-in reset email (still user-only token).
            from django.contrib.auth.forms import PasswordResetForm
            dform = PasswordResetForm({'email': target.email})
            if dform.is_valid():
                dform.save(request=request)
                sent = True
    except Exception as exc:
        messages.error(request, f'Could not send reset link: {exc}')

    record_reset_audit(
        'admin_send_link', request=request, target_user=target,
        target_identifier=target.email, performed_by=request.user,
        notes='Reset link emailed to user.' if sent else 'Send attempt failed.',
    )

    if sent:
        messages.success(
            request,
            f'A password reset link was emailed to {target.get_full_name() or target.username} '
            f'({target.email}). They set their own new password — you never see it.'
        )
    else:
        messages.error(request, 'Failed to send the reset link. Please try again or check email settings.')

    return redirect('user_management')


@login_required
@user_passes_test(is_admin_only)
def reset_user_mfa(request, user_id):
    """
    Admin-initiated MFA reset for the lost-authenticator case. Removes the user's
    two-factor authenticators so they re-enrol at next login. Separate from password
    reset (never combined) and audited. POST-only.

    IMPORTANT (process): verify the user's identity out of band before doing this.
    """
    target = get_object_or_404(User, id=user_id)

    if request.method != 'POST':
        return redirect('user_management')

    from .signals import record_reset_audit

    removed = 0
    try:
        from allauth.mfa.models import Authenticator
        qs = Authenticator.objects.filter(user=target)
        removed = qs.count()
        qs.delete()
    except Exception as exc:
        messages.error(request, f'Could not reset MFA: {exc}')
        record_reset_audit(
            'admin_reset_mfa', request=request, target_user=target,
            target_identifier=target.email or target.username, performed_by=request.user,
            notes=f'FAILED — {exc}',
        )
        return redirect('user_management')

    record_reset_audit(
        'admin_reset_mfa', request=request, target_user=target,
        target_identifier=target.email or target.username, performed_by=request.user,
        notes=f'Removed {removed} authenticator(s); user must re-enrol MFA.',
    )
    messages.success(
        request,
        f"MFA reset for {target.get_full_name() or target.username}. "
        f"They will be prompted to set up two-factor again at next login."
    )
    return redirect('user_management')
