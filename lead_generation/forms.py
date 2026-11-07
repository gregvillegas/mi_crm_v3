from django import forms
from django.forms import inlineformset_factory
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, HTML, Field
from crispy_forms.bootstrap import FormActions
from .models import Lead, LeadSource, LeadActivity, ConversionTracking, LeadNurturingCampaign
from customers.models import Customer
from users.models import User
from django import forms as dj_forms


class MarkLostForm(forms.Form):
    reason = forms.ChoiceField(
        choices=[
            ('not_interested', 'Not Interested'),
            ('budget', 'Budget Constraints'),
            ('competitor', 'Chose Competitor'),
            ('timing', 'Timing Not Right'),
            ('no_response', 'No Response'),
            ('other', 'Other'),
        ],
        required=True,
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Optional notes about why the lead was lost'}),
    )

class LeadForm(forms.ModelForm):
    """Form for creating and editing leads"""
    
    class Meta:
        model = Lead
        fields = [
            'first_name', 'last_name', 'email', 'phone_number', 'company_name', 'job_title',
            'address', 'city', 'territory', 'industry', 'company_size', 'annual_revenue',
            'source', 'assigned_to', 'priority', 'initial_interest', 'requirements',
            'budget_range', 'timeline', 'next_follow_up_date', 'expected_close_date', 'notes'
        ]
        widgets = {
            'initial_interest': forms.Textarea(attrs={'rows': 3}),
            'requirements': forms.Textarea(attrs={'rows': 3}),
            'address': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'next_follow_up_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'expected_close_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter salesperson choices based on user's role and permissions
        if user:
            if user.role in ['salesperson']:
                # Salespeople can only assign to themselves
                self.fields['assigned_to'].queryset = User.objects.filter(id=user.id)
            elif user.role in ['supervisor', 'asm', 'avp']:
                # Managers can assign within their scope
                if user.role == 'supervisor':
                    groups = user.managed_groups.all()
                elif user.role == 'asm':
                    from teams.models import Group
                    groups = Group.objects.filter(team__in=user.asm_teams.all())
                else:
                    from teams.models import Group, Team
                    groups = Group.objects.filter(team__in=Team.objects.filter(avp=user))
                team_members = User.objects.filter(team_membership__group__in=groups, role='salesperson')
                self.fields['assigned_to'].queryset = team_members
            else:
                # Admins and executives see all salespeople
                self.fields['assigned_to'].queryset = User.objects.filter(
                    role='salesperson', is_active=True
                )
        
        self.helper = FormHelper()
        self.helper.layout = Layout(
            HTML('<h4 class="text-primary"><i class="fas fa-user-plus"></i> Lead Information</h4>'),
            Row(
                Column('first_name', css_class='form-group col-md-6 mb-0'),
                Column('last_name', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('email', css_class='form-group col-md-6 mb-0'),
                Column('phone_number', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('company_name', css_class='form-group col-md-8 mb-0'),
                Column('job_title', css_class='form-group col-md-4 mb-0'),
                css_class='form-row'
            ),
            HTML('<hr><h5 class="text-secondary"><i class="fas fa-building"></i> Business Details</h5>'),
            Row(
                Column('industry', css_class='form-group col-md-6 mb-0'),
                Column('territory', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('company_size', css_class='form-group col-md-6 mb-0'),
                Column('annual_revenue', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            'address',
            'city',
            HTML('<hr><h5 class="text-info"><i class="fas fa-chart-line"></i> Lead Management</h5>'),
            Row(
                Column('source', css_class='form-group col-md-4 mb-0'),
                Column('assigned_to', css_class='form-group col-md-4 mb-0'),
                Column('priority', css_class='form-group col-md-4 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('budget_range', css_class='form-group col-md-6 mb-0'),
                Column('timeline', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            HTML('<hr><h5 class="text-warning"><i class="fas fa-clipboard-list"></i> Requirements & Timeline</h5>'),
            'initial_interest',
            'requirements',
            Row(
                Column('next_follow_up_date', css_class='form-group col-md-6 mb-0'),
                Column('expected_close_date', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            'notes',
            FormActions(
                Submit('submit', 'Save Lead', css_class='btn-primary'),
                HTML('<a href="{% url \"lead_generation:lead_list\" %}" class="btn btn-secondary">Cancel</a>')
            )
        )


class LeadImportForm(forms.Form):
    file = forms.FileField()
    calculate_scores = forms.BooleanField(required=False, initial=True)
    default_assigned_to = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        qs = User.objects.filter(role='salesperson', is_active=True)
        if user and user.role == 'salesperson':
            qs = qs.filter(id=user.id)
        elif user and user.role in ['supervisor', 'asm', 'avp']:
            if user.role == 'supervisor':
                groups = user.managed_groups.all()
            elif user.role == 'asm':
                from teams.models import Group
                groups = Group.objects.filter(team__in=user.asm_teams.all())
            else:
                from teams.models import Group, Team
                groups = Group.objects.filter(team__in=Team.objects.filter(avp=user))
            qs = User.objects.filter(team_membership__group__in=groups, role='salesperson')
        self.fields['default_assigned_to'].queryset = qs

    def clean_file(self):
        f = self.cleaned_data.get('file')
        name = (getattr(f, 'name', '') or '').lower()
        if not (name.endswith('.csv') or name.endswith('.xlsx')):
            raise forms.ValidationError('Upload a CSV (.csv) or Excel (.xlsx) file.')
        return f

class LeadActivityForm(forms.ModelForm):
    """Form for logging lead activities"""
    
    class Meta:
        model = LeadActivity
        fields = [
            'activity_type', 'title', 'description', 'outcome', 
            'follow_up_required', 'follow_up_date'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'follow_up_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.helper = FormHelper()
        self.helper.layout = Layout(
            HTML('<h5><i class="fas fa-tasks"></i> Log Activity</h5>'),
            Row(
                Column('activity_type', css_class='form-group col-md-6 mb-0'),
                Column('outcome', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            'title',
            'description',
            HTML('<div class="form-check mt-3">'),
            Field('follow_up_required', css_class='form-check-input'),
            HTML('</div>'),
            'follow_up_date',
            FormActions(
                Submit('submit', 'Log Activity', css_class='btn-success'),
                HTML('<button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>')
            )
        )


class ConversionForm(forms.ModelForm):
    """Form for converting leads to customers"""
    
    create_sales_funnel_entry = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Create a sales funnel entry when converting this lead"
    )
    
    sales_funnel_stage = forms.ChoiceField(
        choices=[],
        required=False,
        help_text="Initial sales funnel stage for the new entry"
    )
    
    class Meta:
        model = ConversionTracking
        fields = ['conversion_value', 'notes']
        widgets = {
            'conversion_value': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Import here to avoid circular imports
        from sales_funnel.models import SalesFunnel
        
        self.fields['sales_funnel_stage'].choices = SalesFunnel.FUNNEL_STAGES
        
        self.helper = FormHelper()
        self.helper.layout = Layout(
            HTML('<h4><i class="fas fa-exchange-alt"></i> Convert Lead to Customer</h4>'),
            HTML('<div class="alert alert-info"><i class="fas fa-info-circle"></i> This will create a new customer record and optionally add them to the sales funnel.</div>'),
            'conversion_value',
            HTML('<div class="form-check mt-3">'),
            Field('create_sales_funnel_entry', css_class='form-check-input'),
            HTML('</div>'),
            'sales_funnel_stage',
            'notes',
            FormActions(
                Submit('submit', 'Convert to Customer', css_class='btn-success'),
                HTML('<a href="javascript:history.back()" class="btn btn-secondary">Cancel</a>')
            )
        )


class LeadFilterForm(forms.Form):
    """Form for filtering leads on the dashboard"""
    
    STATUS_CHOICES = [('', 'All Statuses')] + Lead.STATUS_CHOICES
    PRIORITY_CHOICES = [('', 'All Priorities')] + Lead.PRIORITY_CHOICES
    
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False)
    priority = forms.ChoiceField(choices=PRIORITY_CHOICES, required=False)
    source = forms.ModelChoiceField(queryset=LeadSource.objects.filter(is_active=True), required=False, empty_label="All Sources")
    assigned_to = forms.ModelChoiceField(queryset=User.objects.filter(role='salesperson', is_active=True), required=False, empty_label="All Salespeople")
    
    score_min = forms.IntegerField(
        required=False, 
        widget=forms.NumberInput(attrs={'min': '0', 'max': '100', 'placeholder': 'Min Score'})
    )
    score_max = forms.IntegerField(
        required=False, 
        widget=forms.NumberInput(attrs={'min': '0', 'max': '100', 'placeholder': 'Max Score'})
    )
    
    created_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'placeholder': 'From Date'})
    )
    created_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'placeholder': 'To Date'})
    )
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter salesperson choices based on user permissions
        if user and user.role in ['supervisor', 'asm', 'avp']:
            if user.role == 'supervisor':
                groups = user.managed_groups.all()
            elif user.role == 'asm':
                from teams.models import Group
                groups = Group.objects.filter(team__in=user.asm_teams.all())
            else:
                from teams.models import Group, Team
                groups = Group.objects.filter(team__in=Team.objects.filter(avp=user))
            team_members = User.objects.filter(team_membership__group__in=groups, role='salesperson')
            self.fields['assigned_to'].queryset = team_members
        
        self.helper = FormHelper()
        self.helper.form_method = 'get'
        self.helper.layout = Layout(
            Row(
                Column('status', css_class='form-group col-md-3 mb-0'),
                Column('priority', css_class='form-group col-md-3 mb-0'),
                Column('source', css_class='form-group col-md-3 mb-0'),
                Column('assigned_to', css_class='form-group col-md-3 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('score_min', css_class='form-group col-md-2 mb-0'),
                Column('score_max', css_class='form-group col-md-2 mb-0'),
                Column('created_from', css_class='form-group col-md-4 mb-0'),
                Column('created_to', css_class='form-group col-md-4 mb-0'),
                css_class='form-row'
            ),
            FormActions(
                Submit('filter', 'Apply Filters', css_class='btn-primary'),
                HTML('<a href="{% url \"lead_generation:lead_list\" %}" class="btn btn-outline-secondary">Clear</a>')
            )
        )


class LeadSourceForm(forms.ModelForm):
    """Form for managing lead sources"""
    
    class Meta:
        model = LeadSource
        fields = ['name', 'source_type', 'description', 'cost_per_lead', 'is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'cost_per_lead': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }


class LeadSourceCostUpdateForm(forms.Form):
    """Validate an inline lead-source cost update."""

    cost_per_lead = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
    )


class BulkLeadActionForm(forms.Form):
    """Form for performing bulk actions on leads"""
    
    ACTION_CHOICES = [
        ('assign_salesperson', 'Assign Salesperson'),
        ('update_priority', 'Update Priority'),
        ('update_status', 'Update Status'),
    ]
    
    action = forms.ChoiceField(choices=ACTION_CHOICES)
    salesperson = forms.ModelChoiceField(
        queryset=User.objects.filter(role='salesperson', is_active=True),
        required=False
    )
    priority = forms.ChoiceField(choices=Lead.PRIORITY_CHOICES, required=False)
    status = forms.ChoiceField(choices=Lead.STATUS_CHOICES, required=False)
