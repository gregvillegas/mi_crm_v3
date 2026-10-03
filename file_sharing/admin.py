from django.contrib import admin
from django.utils.html import format_html
from .models import (
    GroupFileShare, FileCategory, FileAccessLog,
    CompanyFileShare, CompanyFileAccessLog,
)

@admin.register(FileCategory)
class FileCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'icon']
    search_fields = ['name', 'description']
    ordering = ['name']

class FileAccessLogInline(admin.TabularInline):
    model = FileAccessLog
    extra = 0
    readonly_fields = ['user', 'action', 'timestamp', 'ip_address']
    can_delete = False
    
    def has_add_permission(self, request, obj=None):
        return False

@admin.register(GroupFileShare)
class GroupFileShareAdmin(admin.ModelAdmin):
    list_display = ['title', 'group', 'category', 'uploaded_by', 'uploaded_at', 'file_size_display', 'download_count', 'is_active']
    list_filter = ['category', 'group__team', 'group', 'is_active', 'uploaded_at']
    search_fields = ['title', 'description', 'group__name', 'uploaded_by__username']
    readonly_fields = ['uploaded_at', 'updated_at', 'file_size', 'mime_type', 'download_count']
    inlines = [FileAccessLogInline]
    
    fieldsets = (
        ('File Information', {
            'fields': ('title', 'description', 'file', 'category')
        }),
        ('Group & Access', {
            'fields': ('group', 'uploaded_by', 'is_active')
        }),
        ('Metadata', {
            'fields': ('file_size', 'mime_type', 'download_count', 'uploaded_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def file_size_display(self, obj):
        return obj.get_file_size_display()
    file_size_display.short_description = 'File Size'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('group', 'group__team', 'uploaded_by')

@admin.register(FileAccessLog)
class FileAccessLogAdmin(admin.ModelAdmin):
    list_display = ['file_share', 'user', 'action', 'timestamp', 'ip_address']
    list_filter = ['action', 'timestamp', 'file_share__category']
    search_fields = ['file_share__title', 'user__username', 'ip_address']
    readonly_fields = ['file_share', 'user', 'action', 'timestamp', 'ip_address', 'user_agent']
    ordering = ['-timestamp']
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('file_share', 'user')


class CompanyFileAccessLogInline(admin.TabularInline):
    model = CompanyFileAccessLog
    extra = 0
    readonly_fields = ['user', 'action', 'timestamp', 'ip_address']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CompanyFileShare)
class CompanyFileShareAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'uploaded_by', 'uploaded_at', 'download_count', 'is_active']
    list_filter = ['category', 'is_active', 'uploaded_at']
    search_fields = ['title', 'description', 'uploaded_by__username']
    readonly_fields = ['uploaded_at', 'updated_at', 'file_size', 'mime_type', 'download_count']
    inlines = [CompanyFileAccessLogInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('uploaded_by')


@admin.register(CompanyFileAccessLog)
class CompanyFileAccessLogAdmin(admin.ModelAdmin):
    list_display = ['file_share', 'user', 'action', 'timestamp', 'ip_address']
    list_filter = ['action', 'timestamp']
    search_fields = ['file_share__title', 'user__username', 'ip_address']
    readonly_fields = ['file_share', 'user', 'action', 'timestamp', 'ip_address', 'user_agent']
    ordering = ['-timestamp']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
