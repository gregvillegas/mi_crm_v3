from django import forms
from django.core.exceptions import ValidationError
from .models import GroupFileShare, CompanyFileShare, FileCategory
from teams.models import Group

class FileUploadForm(forms.ModelForm):
    """Form for uploading files to a group"""
    
    class Meta:
        model = GroupFileShare
        fields = ['title', 'description', 'file', 'category']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Enter a descriptive title for the file'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 3,
                'placeholder': 'Optional description of the file contents'
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.rtf,.jpg,.jpeg,.png,.gif,.zip,.rar'
            }),
            'category': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.group = kwargs.pop('group', None)
        super().__init__(*args, **kwargs)
        
        # Add help text for file upload
        self.fields['file'].help_text = (
            'Supported formats: PDF, Word, Excel, PowerPoint, Text, Images (JPG, PNG, GIF), Archives (ZIP, RAR). '
            'Maximum file size: 50MB'
        )
        
        # Make title required with better help text
        self.fields['title'].help_text = 'Give your file a clear, descriptive title'
        
        # Set category help text
        self.fields['category'].help_text = 'Choose the most appropriate category for this file'
    
    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            # Additional validation can be added here
            if file.size > 50 * 1024 * 1024:  # 50MB
                raise ValidationError('File size cannot exceed 50MB.')
        return file
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.group:
            instance.group = self.group
        if commit:
            instance.save()
        return instance

class FileFilterForm(forms.Form):
    """Form for filtering files by category"""
    category = forms.ChoiceField(
        choices=[('all', 'All Categories')] + list(FileCategory.CATEGORY_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    search = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search files by title or description...'
        })
    )

class FileEditForm(forms.ModelForm):
    """Form for editing file details (not the file itself)"""
    
    class Meta:
        model = GroupFileShare
        fields = ['title', 'description', 'category', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['is_active'].help_text = 'Uncheck to temporarily disable file downloads'


class CompanyFileUploadForm(forms.ModelForm):
    """Upload a file to the company-wide share (no group)."""

    class Meta:
        model = CompanyFileShare
        fields = ['title', 'description', 'file', 'category']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter a descriptive title for the file'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Optional description of the file contents'
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.rtf,.csv,.jpg,.jpeg,.png,.gif,.zip,.rar,.apk'
            }),
            'category': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['file'].help_text = (
            'Shared with everyone. Supported: PDF, Office docs, images, archives, and APK. '
            'Maximum file size: 150MB.'
        )
        self.fields['title'].help_text = 'Give your file a clear, descriptive title'
        self.fields['category'].help_text = 'Choose the most appropriate category for this file'

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file and file.size > 150 * 1024 * 1024:  # 150MB
            raise ValidationError('File size cannot exceed 150MB.')
        return file


class CompanyFileEditForm(forms.ModelForm):
    """Edit company file details (not the file itself)."""

    class Meta:
        model = CompanyFileShare
        fields = ['title', 'description', 'category', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['is_active'].help_text = 'Uncheck to temporarily hide this file from everyone'
