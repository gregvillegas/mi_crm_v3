import os
from django.db import models
from django.contrib.auth import get_user_model
from teams.models import Group
from django.core.exceptions import ValidationError
from django.utils import timezone

User = get_user_model()

def get_file_upload_path(instance, filename):
    """Generate upload path: group_files/group_id/category/filename"""
    return f'group_files/{instance.group.id}/{instance.category}/{filename}'

def validate_file_size(value):
    """Validate file size - max 50MB"""
    limit = 50 * 1024 * 1024  # 50MB
    if value.size > limit:
        raise ValidationError('File too large. Size should not exceed 50 MB.')

def validate_file_extension(value):
    """Validate allowed file extensions"""
    allowed_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', 
                         '.txt', '.rtf', '.jpg', '.jpeg', '.png', '.gif', '.zip', '.rar']
    ext = os.path.splitext(value.name)[1]
    if not ext.lower() in allowed_extensions:
        raise ValidationError(f'Unsupported file extension. Allowed: {", ".join(allowed_extensions)}')

class FileCategory(models.Model):
    """Categories for organizing shared files"""
    CATEGORY_CHOICES = [
        ('proposals', 'Proposal Templates'),
        ('contracts', 'Contracts'),
        ('presentations', 'Presentations'),
        ('forms', 'Forms & Documents'),
        ('resources', 'Resources & Guidelines'),
        ('training', 'Training Materials'),
        ('other', 'Other Documents'),
    ]
    
    name = models.CharField(max_length=50, choices=CATEGORY_CHOICES, unique=True)
    description = models.TextField(blank=True, help_text='Optional description of this category')
    icon = models.CharField(max_length=50, default='📄', help_text='Icon for this category')
    
    def __str__(self):
        return dict(self.CATEGORY_CHOICES)[self.name]
    
    class Meta:
        verbose_name_plural = 'File Categories'
        ordering = ['name']

class GroupFileShare(models.Model):
    """Shared files for a group"""
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='shared_files')
    title = models.CharField(max_length=200, help_text='Descriptive title for the file')
    description = models.TextField(blank=True, help_text='Optional description of the file contents')
    file = models.FileField(
        upload_to=get_file_upload_path,
        validators=[validate_file_size, validate_file_extension]
    )
    category = models.CharField(
        max_length=50, 
        choices=FileCategory.CATEGORY_CHOICES,
        default='other'
    )
    
    # Metadata
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_files')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Access control
    is_active = models.BooleanField(default=True, help_text='Whether this file is available for download')
    download_count = models.PositiveIntegerField(default=0, help_text='Number of times this file has been downloaded')
    
    # File metadata
    file_size = models.PositiveIntegerField(null=True, blank=True, help_text='File size in bytes')
    mime_type = models.CharField(max_length=100, blank=True)
    
    def save(self, *args, **kwargs):
        if self.file:
            self.file_size = self.file.size
            # Try to determine mime type from file extension
            ext = os.path.splitext(self.file.name)[1].lower()
            mime_map = {
                '.pdf': 'application/pdf',
                '.doc': 'application/msword',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.xls': 'application/vnd.ms-excel',
                '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                '.ppt': 'application/vnd.ms-powerpoint',
                '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                '.txt': 'text/plain',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.zip': 'application/zip',
                '.rar': 'application/x-rar-compressed',
            }
            self.mime_type = mime_map.get(ext, 'application/octet-stream')
        super().save(*args, **kwargs)
    
    def get_file_size_display(self):
        """Return human readable file size"""
        if not self.file_size:
            return 'Unknown'
        
        for unit in ['bytes', 'KB', 'MB', 'GB']:
            if self.file_size < 1024.0:
                return f"{self.file_size:.1f} {unit}"
            self.file_size /= 1024.0
        return f"{self.file_size:.1f} TB"
    
    def get_category_display(self):
        """Return display name for category"""
        return dict(FileCategory.CATEGORY_CHOICES)[self.category]
    
    def get_category_icon(self):
        """Return icon for category"""
        icons = {
            'proposals': '📋',
            'contracts': '📄',
            'presentations': '📊', 
            'forms': '📝',
            'resources': '📚',
            'training': '🎓',
            'other': '📁',
        }
        return icons.get(self.category, '📄')
    
    def __str__(self):
        return f"{self.title} ({self.group.name})"
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Group File Share'
        verbose_name_plural = 'Group File Shares'

class FileAccessLog(models.Model):
    """Log file access for auditing purposes"""
    ACTION_CHOICES = [
        ('download', 'Downloaded'),
        ('view', 'Viewed'),
        ('upload', 'Uploaded'),
        ('delete', 'Deleted'),
    ]
    
    file_share = models.ForeignKey(GroupFileShare, on_delete=models.CASCADE, related_name='access_logs')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='file_access_logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.user.username} {self.action} {self.file_share.title} at {self.timestamp}"
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'File Access Log'
        verbose_name_plural = 'File Access Logs'


# ---------------------------------------------------------------------------
# Company-wide file share
#
# A single library every team/group can read (e.g. the mobile APK, company
# forms, price lists). Unlike GroupFileShare it has NO group — it's visible to
# all authenticated users. Upload/manage is restricted to executives in the
# views layer. Kept as a separate model so the existing group-scoped logic is
# untouched.
# ---------------------------------------------------------------------------

def get_company_file_upload_path(instance, filename):
    """Upload path: company_files/<category>/<filename>"""
    return f'company_files/{instance.category}/{filename}'


def validate_company_file_extension(value):
    """
    Allowed extensions for the company share. Superset of the group list plus
    .apk so the Android build can be distributed here.
    """
    allowed_extensions = [
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
        '.txt', '.rtf', '.csv', '.jpg', '.jpeg', '.png', '.gif',
        '.zip', '.rar', '.apk',
    ]
    ext = os.path.splitext(value.name)[1]
    if ext.lower() not in allowed_extensions:
        raise ValidationError(f'Unsupported file extension. Allowed: {", ".join(allowed_extensions)}')


def validate_company_file_size(value):
    """Validate file size - max 150MB (APKs can be larger than office docs)."""
    limit = 150 * 1024 * 1024  # 150MB
    if value.size > limit:
        raise ValidationError('File too large. Size should not exceed 150 MB.')


class CompanyFileShare(models.Model):
    """A company-wide shared file, readable by every authenticated user."""
    title = models.CharField(max_length=200, help_text='Descriptive title for the file')
    description = models.TextField(blank=True, help_text='Optional description of the file contents')
    file = models.FileField(
        upload_to=get_company_file_upload_path,
        validators=[validate_company_file_size, validate_company_file_extension],
    )
    category = models.CharField(
        max_length=50,
        choices=FileCategory.CATEGORY_CHOICES,
        default='other',
    )

    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_company_files')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_active = models.BooleanField(default=True, help_text='Whether this file is available for download')
    download_count = models.PositiveIntegerField(default=0, help_text='Number of times this file has been downloaded')

    file_size = models.PositiveIntegerField(null=True, blank=True, help_text='File size in bytes')
    mime_type = models.CharField(max_length=100, blank=True)

    def save(self, *args, **kwargs):
        if self.file:
            self.file_size = self.file.size
            ext = os.path.splitext(self.file.name)[1].lower()
            mime_map = {
                '.pdf': 'application/pdf',
                '.doc': 'application/msword',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                '.xls': 'application/vnd.ms-excel',
                '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                '.ppt': 'application/vnd.ms-powerpoint',
                '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                '.txt': 'text/plain',
                '.csv': 'text/csv',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.zip': 'application/zip',
                '.rar': 'application/x-rar-compressed',
                '.apk': 'application/vnd.android.package-archive',
            }
            self.mime_type = mime_map.get(ext, 'application/octet-stream')
        super().save(*args, **kwargs)

    def get_file_size_display(self):
        """Return human readable file size."""
        size = self.file_size
        if not size:
            return 'Unknown'
        for unit in ['bytes', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    def get_category_display(self):
        return dict(FileCategory.CATEGORY_CHOICES)[self.category]

    def get_category_icon(self):
        icons = {
            'proposals': '📋', 'contracts': '📄', 'presentations': '📊',
            'forms': '📝', 'resources': '📚', 'training': '🎓', 'other': '📁',
        }
        return icons.get(self.category, '📄')

    def __str__(self):
        return f"{self.title} (Company)"

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Company File Share'
        verbose_name_plural = 'Company File Shares'


class CompanyFileAccessLog(models.Model):
    """Audit log for company-wide file access (mirrors FileAccessLog)."""
    ACTION_CHOICES = [
        ('download', 'Downloaded'),
        ('view', 'Viewed'),
        ('upload', 'Uploaded'),
        ('delete', 'Deleted'),
    ]

    file_share = models.ForeignKey(CompanyFileShare, on_delete=models.CASCADE, related_name='access_logs')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='company_file_access_logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    def __str__(self):
        return f"{self.user.username} {self.action} {self.file_share.title} at {self.timestamp}"

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Company File Access Log'
        verbose_name_plural = 'Company File Access Logs'
