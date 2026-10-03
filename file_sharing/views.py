import os
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, Http404, FileResponse
from django.db.models import Q
from django.utils import timezone
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.urls import reverse

from .models import GroupFileShare, FileAccessLog, FileCategory
from .forms import FileUploadForm, FileFilterForm, FileEditForm
from teams.models import Group, TeamMembership
from users.models import User

def get_user_groups(user):
    """Get all groups that a user has access to"""
    if user.role in ['admin', 'president', 'gm', 'vp']:
        # Executives can access all groups
        return Group.objects.all()
    elif user.role == 'avp':
        # AVP can access groups in their teams
        from teams.models import Team
        user_teams = Team.objects.filter(avp=user)
        return Group.objects.filter(team__in=user_teams)
    elif user.role == 'asm':
        # ASM can access groups in their assigned teams
        user_teams = user.asm_teams.all()
        return Group.objects.filter(team__in=user_teams)
    elif user.role == 'sm':
        # SM can access only their explicitly assigned groups
        return user.sm_groups.all()
    elif user.role == 'supervisor':
        # Supervisor can access groups they manage
        return user.managed_groups.all()
    elif user.role == 'teamlead':
        # Team lead can access groups they lead
        return user.led_groups.all()
    else:
        # Sales agents can access their own group
        try:
            membership = TeamMembership.objects.get(user=user)
            return Group.objects.filter(id=membership.group.id)
        except TeamMembership.DoesNotExist:
            return Group.objects.none()

def user_can_access_group(user, group):
    """Check if user can access a specific group"""
    accessible_groups = get_user_groups(user)
    return group in accessible_groups

def user_can_upload_files(user, group):
    """Check if user can upload files to a group"""
    # All users who can access a group can upload files
    return user_can_access_group(user, group)

def user_can_delete_file(user, file_share):
    """Check if user can delete a file"""
    # Admin, executives, and file uploader can delete
    if user.role in ['admin', 'president', 'gm', 'vp']:
        return True
    if file_share.uploaded_by == user:
        return True
    # Group managers can delete files
    if user.role == 'avp' and file_share.group.team.avp == user:
        return True
    if user.role in ['asm', 'supervisor'] and file_share.group.supervisor == user:
        return True
    if user.role == 'teamlead' and file_share.group.teamlead == user:
        return True
    return False

def log_file_access(file_share, user, action, request=None):
    """Log file access for auditing"""
    ip_address = None
    user_agent = ''
    
    if request:
        # Get real IP address
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip_address = x_forwarded_for.split(',')[0]
        else:
            ip_address = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')
    
    FileAccessLog.objects.create(
        file_share=file_share,
        user=user,
        action=action,
        ip_address=ip_address,
        user_agent=user_agent
    )

@login_required
def group_files(request, group_id):
    """List files for a specific group"""
    group = get_object_or_404(Group, id=group_id)
    
    # Check access permissions
    if not user_can_access_group(request.user, group):
        raise Http404("You don't have permission to access this group's files.")
    
    # Get files for this group
    files = GroupFileShare.objects.filter(group=group, is_active=True)
    
    # Apply filters if provided
    filter_form = FileFilterForm(request.GET)
    if filter_form.is_valid():
        category = filter_form.cleaned_data.get('category')
        search = filter_form.cleaned_data.get('search')
        
        if category and category != 'all':
            files = files.filter(category=category)
        
        if search:
            files = files.filter(
                Q(title__icontains=search) | 
                Q(description__icontains=search)
            )
    
    # Pagination
    paginator = Paginator(files, 20)  # Show 20 files per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Group files by category for better organization
    files_by_category = {}
    for file_share in page_obj:
        category = file_share.category
        if category not in files_by_category:
            files_by_category[category] = []
        files_by_category[category].append(file_share)
    
    context = {
        'group': group,
        'files': page_obj,
        'files_by_category': files_by_category,
        'filter_form': filter_form,
        'can_upload': user_can_upload_files(request.user, group),
        'total_files': files.count(),
    }
    
    return render(request, 'file_sharing/group_files.html', context)

@login_required
def upload_file(request, group_id):
    """Upload a file to a group"""
    group = get_object_or_404(Group, id=group_id)
    
    # Check upload permissions
    if not user_can_upload_files(request.user, group):
        raise Http404("You don't have permission to upload files to this group.")
    
    if request.method == 'POST':
        form = FileUploadForm(request.POST, request.FILES, group=group)
        if form.is_valid():
            file_share = form.save(commit=False)
            file_share.uploaded_by = request.user
            file_share.save()
            
            # Log the upload
            log_file_access(file_share, request.user, 'upload', request)
            
            messages.success(request, f'File "{file_share.title}" uploaded successfully!')
            return redirect('group_files', group_id=group.id)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = FileUploadForm(group=group)
    
    context = {
        'form': form,
        'group': group,
        'title': f'Upload File to {group.name}'
    }
    
    return render(request, 'file_sharing/upload_file.html', context)

@login_required
def download_file(request, file_id):
    """Download a file"""
    file_share = get_object_or_404(GroupFileShare, id=file_id, is_active=True)
    
    # Check access permissions
    if not user_can_access_group(request.user, file_share.group):
        raise Http404("You don't have permission to access this file.")
    
    try:
        # Log the download
        log_file_access(file_share, request.user, 'download', request)
        
        # Increment download counter
        file_share.download_count += 1
        file_share.save(update_fields=['download_count'])
        
        # Serve the file
        response = FileResponse(
            open(file_share.file.path, 'rb'),
            as_attachment=True,
            filename=os.path.basename(file_share.file.name)
        )
        response['Content-Type'] = file_share.mime_type
        return response
        
    except FileNotFoundError:
        messages.error(request, 'File not found on server.')
        return redirect('group_files', group_id=file_share.group.id)

@login_required
def view_file(request, file_id):
    """View a file in the browser (without forcing download)"""
    file_share = get_object_or_404(GroupFileShare, id=file_id, is_active=True)
    
    # Check access permissions
    if not user_can_access_group(request.user, file_share.group):
        raise Http404("You don't have permission to access this file.")
    
    try:
        # Log the view (only log as 'view' not 'download' since user is just viewing)
        log_file_access(file_share, request.user, 'view', request)
        
        # Serve the file for inline viewing (not as attachment)
        response = FileResponse(
            open(file_share.file.path, 'rb'),
            as_attachment=False,  # This allows viewing in browser
            filename=os.path.basename(file_share.file.name)
        )
        response['Content-Type'] = file_share.mime_type
        response['Content-Disposition'] = f'inline; filename="{os.path.basename(file_share.file.name)}"'
        return response
        
    except FileNotFoundError:
        messages.error(request, 'File not found on server.')
        return redirect('group_files', group_id=file_share.group.id)

@login_required
def file_details(request, file_id):
    """View file details"""
    file_share = get_object_or_404(GroupFileShare, id=file_id)
    
    # Check access permissions
    if not user_can_access_group(request.user, file_share.group):
        raise Http404("You don't have permission to access this file.")
    
    # Log the view
    log_file_access(file_share, request.user, 'view', request)
    
    # Get recent access logs for this file (last 10)
    recent_logs = file_share.access_logs.select_related('user').order_by('-timestamp')[:10]
    
    context = {
        'file_share': file_share,
        'recent_logs': recent_logs,
        'can_delete': user_can_delete_file(request.user, file_share),
        'can_edit': user_can_delete_file(request.user, file_share),  # Same permissions for edit
    }
    
    return render(request, 'file_sharing/file_details.html', context)

@login_required
def edit_file(request, file_id):
    """Edit file details"""
    file_share = get_object_or_404(GroupFileShare, id=file_id)
    
    # Check edit permissions
    if not user_can_delete_file(request.user, file_share):
        raise Http404("You don't have permission to edit this file.")
    
    if request.method == 'POST':
        form = FileEditForm(request.POST, instance=file_share)
        if form.is_valid():
            form.save()
            messages.success(request, f'File "{file_share.title}" updated successfully!')
            return redirect('file_details', file_id=file_share.id)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = FileEditForm(instance=file_share)
    
    context = {
        'form': form,
        'file_share': file_share,
        'title': f'Edit {file_share.title}'
    }
    
    return render(request, 'file_sharing/edit_file.html', context)

@login_required
@require_http_methods(["POST"])
def delete_file(request, file_id):
    """Delete a file"""
    file_share = get_object_or_404(GroupFileShare, id=file_id)
    
    # Check delete permissions
    if not user_can_delete_file(request.user, file_share):
        raise Http404("You don't have permission to delete this file.")
    
    group_id = file_share.group.id
    file_title = file_share.title
    
    # Log the deletion before deleting
    log_file_access(file_share, request.user, 'delete', request)
    
    # Delete the actual file from filesystem
    if file_share.file and os.path.exists(file_share.file.path):
        try:
            os.remove(file_share.file.path)
        except OSError:
            pass  # File already deleted or permission issue
    
    # Delete the database record
    file_share.delete()
    
    messages.success(request, f'File "{file_title}" deleted successfully!')
    return redirect('group_files', group_id=group_id)

@login_required
def my_files(request):
    """List files uploaded by the current user"""
    files = GroupFileShare.objects.filter(uploaded_by=request.user).select_related('group')
    
    # Apply filters
    filter_form = FileFilterForm(request.GET)
    if filter_form.is_valid():
        category = filter_form.cleaned_data.get('category')
        search = filter_form.cleaned_data.get('search')
        
        if category and category != 'all':
            files = files.filter(category=category)
        
        if search:
            files = files.filter(
                Q(title__icontains=search) | 
                Q(description__icontains=search)
            )
    
    # Pagination
    paginator = Paginator(files, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'files': page_obj,
        'filter_form': filter_form,
        'title': 'My Uploaded Files',
        'total_files': files.count(),
    }
    
    return render(request, 'file_sharing/my_files.html', context)

@login_required
def quick_upload(request):
    """Quick upload - redirect to user's primary group upload page"""
    accessible_groups = get_user_groups(request.user)
    
    if not accessible_groups.exists():
        messages.error(request, "You don't have access to any groups.")
        return redirect('all_files')
    
    # Try to find user's primary group (from team membership)
    try:
        membership = TeamMembership.objects.get(user=request.user)
        primary_group = membership.group
        if primary_group in accessible_groups:
            return redirect('upload_file', group_id=primary_group.id)
    except TeamMembership.DoesNotExist:
        pass
    
    # Fall back to first accessible group
    first_group = accessible_groups.first()
    return redirect('upload_file', group_id=first_group.id)

@login_required
def upload_selector(request):
    """Show group selection page for file upload"""
    accessible_groups = get_user_groups(request.user)
    
    if not accessible_groups.exists():
        messages.error(request, "You don't have access to any groups.")
        return redirect('all_files')
    
    # If user has only one group, redirect directly
    if accessible_groups.count() == 1:
        group = accessible_groups.first()
        return redirect('upload_file', group_id=group.id)
    
    context = {
        'groups': accessible_groups,
        'title': 'Select Group for File Upload'
    }
    
    return render(request, 'file_sharing/upload_selector.html', context)

@login_required
def all_groups_files(request):
    """List all files from groups user has access to"""
    accessible_groups = get_user_groups(request.user)
    files = GroupFileShare.objects.filter(
        group__in=accessible_groups,
        is_active=True
    ).select_related('group', 'uploaded_by')
    
    # Apply filters
    filter_form = FileFilterForm(request.GET)
    if filter_form.is_valid():
        category = filter_form.cleaned_data.get('category')
        search = filter_form.cleaned_data.get('search')
        
        if category and category != 'all':
            files = files.filter(category=category)
        
        if search:
            files = files.filter(
                Q(title__icontains=search) | 
                Q(description__icontains=search) |
                Q(group__name__icontains=search)
            )
    
    # Pagination
    paginator = Paginator(files, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'files': page_obj,
        'filter_form': filter_form,
        'title': 'All Group Files',
        'total_files': files.count(),
        'accessible_groups': accessible_groups,
    }
    
    return render(request, 'file_sharing/all_files.html', context)


# ---------------------------------------------------------------------------
# Company-wide file share
#
# Readable by every authenticated user (all teams/groups). Upload/edit are
# restricted to executives; delete is allowed for execs and the uploader.
# ---------------------------------------------------------------------------
from .models import CompanyFileShare, CompanyFileAccessLog
from .forms import CompanyFileUploadForm, CompanyFileEditForm

COMPANY_FILE_MANAGER_ROLES = ['admin', 'president', 'gm', 'vp']


def user_can_manage_company_files(user):
    """Who may upload / edit company-wide files."""
    return getattr(user, 'role', None) in COMPANY_FILE_MANAGER_ROLES


def user_can_delete_company_file(user, file_share):
    """Execs may delete any; the uploader may delete their own."""
    if user_can_manage_company_files(user):
        return True
    return file_share.uploaded_by_id == user.id


def log_company_file_access(file_share, user, action, request=None):
    """Audit company-file access (mirrors log_file_access)."""
    ip_address = None
    user_agent = ''
    if request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip_address = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT', '')
    CompanyFileAccessLog.objects.create(
        file_share=file_share, user=user, action=action,
        ip_address=ip_address, user_agent=user_agent,
    )


@login_required
def company_files(request):
    """List company-wide shared files — visible to every authenticated user."""
    files = CompanyFileShare.objects.filter(is_active=True).select_related('uploaded_by')

    filter_form = FileFilterForm(request.GET)
    if filter_form.is_valid():
        category = filter_form.cleaned_data.get('category')
        search = filter_form.cleaned_data.get('search')
        if category and category != 'all':
            files = files.filter(category=category)
        if search:
            files = files.filter(Q(title__icontains=search) | Q(description__icontains=search))

    paginator = Paginator(files, 24)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'files': page_obj,
        'filter_form': filter_form,
        'title': 'Company Shared Files',
        'total_files': files.count(),
        'can_manage': user_can_manage_company_files(request.user),
    }
    return render(request, 'file_sharing/company_files.html', context)


@login_required
def company_upload(request):
    """Upload a file to the company-wide share (executives only)."""
    if not user_can_manage_company_files(request.user):
        raise Http404("You don't have permission to upload company-wide files.")

    if request.method == 'POST':
        form = CompanyFileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file_share = form.save(commit=False)
            file_share.uploaded_by = request.user
            file_share.save()
            log_company_file_access(file_share, request.user, 'upload', request)
            messages.success(request, f'File "{file_share.title}" shared company-wide!')
            return redirect('company_files')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CompanyFileUploadForm()

    return render(request, 'file_sharing/company_upload.html', {
        'form': form,
        'title': 'Upload Company-wide File',
    })


@login_required
def company_edit(request, file_id):
    """Edit company file details (executives only)."""
    file_share = get_object_or_404(CompanyFileShare, id=file_id)
    if not user_can_manage_company_files(request.user):
        raise Http404("You don't have permission to edit company-wide files.")

    if request.method == 'POST':
        form = CompanyFileEditForm(request.POST, instance=file_share)
        if form.is_valid():
            form.save()
            messages.success(request, f'File "{file_share.title}" updated!')
            return redirect('company_files')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CompanyFileEditForm(instance=file_share)

    return render(request, 'file_sharing/company_upload.html', {
        'form': form,
        'title': f'Edit {file_share.title}',
        'is_edit': True,
    })


@login_required
def company_download(request, file_id):
    """Download a company-wide file — any authenticated user."""
    file_share = get_object_or_404(CompanyFileShare, id=file_id, is_active=True)
    try:
        log_company_file_access(file_share, request.user, 'download', request)
        file_share.download_count += 1
        file_share.save(update_fields=['download_count'])
        response = FileResponse(
            open(file_share.file.path, 'rb'),
            as_attachment=True,
            filename=os.path.basename(file_share.file.name),
        )
        response['Content-Type'] = file_share.mime_type
        return response
    except FileNotFoundError:
        messages.error(request, 'File not found on server.')
        return redirect('company_files')


@login_required
def company_view(request, file_id):
    """View a company-wide file inline — any authenticated user."""
    file_share = get_object_or_404(CompanyFileShare, id=file_id, is_active=True)
    try:
        log_company_file_access(file_share, request.user, 'view', request)
        response = FileResponse(
            open(file_share.file.path, 'rb'),
            as_attachment=False,
            filename=os.path.basename(file_share.file.name),
        )
        response['Content-Type'] = file_share.mime_type
        response['Content-Disposition'] = f'inline; filename="{os.path.basename(file_share.file.name)}"'
        return response
    except FileNotFoundError:
        messages.error(request, 'File not found on server.')
        return redirect('company_files')


@login_required
@require_http_methods(["POST"])
def company_delete(request, file_id):
    """Delete a company-wide file (execs or the uploader)."""
    file_share = get_object_or_404(CompanyFileShare, id=file_id)
    if not user_can_delete_company_file(request.user, file_share):
        raise Http404("You don't have permission to delete this file.")

    file_title = file_share.title
    log_company_file_access(file_share, request.user, 'delete', request)
    if file_share.file and os.path.exists(file_share.file.path):
        try:
            os.remove(file_share.file.path)
        except OSError:
            pass
    file_share.delete()
    messages.success(request, f'File "{file_title}" deleted.')
    return redirect('company_files')
