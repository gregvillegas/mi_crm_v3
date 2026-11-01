from django import forms
from django.core.validators import MinValueValidator, MaxValueValidator
from .models import SalesFunnel
from customers.models import Customer
from users.models import User

class SalesFunnelForm(forms.ModelForm):
    probability = forms.TypedChoiceField(
        choices=[(100, '100'), (75, '75'), (50, '50'), (25, '25')],
        coerce=int,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = SalesFunnel
        fields = [
            'date_created', 'company_name', 'brand', 'requirement_description',
            'cost', 'retail', 'stage', 'customer', 'expected_close_date',
            'probability', 'notes', 'offering_type'
        ]
        widgets = {
            'date_created': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'company_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter company name'
            }),
            'brand': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter brand (e.g. Cisco, IBM, Dell)'
            }),
            'requirement_description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe the customer requirements...'
            }),
            'cost': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00'
            }),
            'retail': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00'
            }),
            'stage': forms.Select(attrs={
                'class': 'form-select'
            }),
            'customer': forms.Select(attrs={
                'class': 'form-select'
            }),
            'expected_close_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Additional notes (optional)...'
            })
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Set today as default date
        if not self.instance.pk:
            from django.utils import timezone
            self.fields['date_created'].initial = timezone.now().date()
        
        # Filter customers based on user access
        if user:
            if user.role == 'salesperson':
                # Salespeople can only see their own customers
                self.fields['customer'].queryset = Customer.objects.filter(
                    salesperson=user, is_active=True
                ).order_by('company_name')
            elif user.role in ['technical_sales', 'techmgr', 'asst_techmgr']:
                # Technical Sales / Technical Manager are scoped to the customers
                # of the team(s) they cover — reuse the shared customer-visibility
                # helper so the funnel picker matches the rest of the app.
                from customers.permissions import visible_customers_queryset
                self.fields['customer'].queryset = visible_customers_queryset(user).filter(
                    is_active=True
                ).order_by('company_name')
            elif user.role in ['supervisor', 'teamlead', 'asm', 'avp']:
                # Managers can see customers in their scope
                # For now, show all active customers - this can be refined based on hierarchy
                self.fields['customer'].queryset = Customer.objects.filter(
                    is_active=True
                ).order_by('company_name')
            else:
                # Admins and executives see all
                self.fields['customer'].queryset = Customer.objects.filter(
                    is_active=True
                ).order_by('company_name')
        
        # Make customer field optional
        self.fields['customer'].empty_label = "-- Select existing customer (optional) --"
        
        # Add helpful labels
        self.fields['cost'].label = "Cost (₱)"
        self.fields['retail'].label = "SRP (₱)"
        self.fields['probability'].label = "Win Probability (%)"
        if 'offering_type' in self.fields:
            self.fields['offering_type'].label = "Technical offering (optional)"
        if self.instance.pk and self.instance.probability is not None:
            existing = int(self.instance.probability)
            existing_values = {int(v) for v, _ in self.fields['probability'].choices}
            if existing not in existing_values:
                self.fields['probability'].choices = [(existing, str(existing))] + list(self.fields['probability'].choices)
        
    def clean(self):
        cleaned_data = super().clean()
        cost = cleaned_data.get('cost')
        retail = cleaned_data.get('retail')
        probability = cleaned_data.get('probability')
        
        # Validate cost vs retail
        if cost is not None and retail is not None:
            if retail < cost:
                raise forms.ValidationError("SRP cannot be less than cost.")
        
        # Validate probability range
        if probability is not None:
            if probability < 0 or probability > 100:
                raise forms.ValidationError("Probability must be between 0 and 100.")
        
        return cleaned_data


from teams.models import (
    Team,
    Group,
    TeamMembership,
    asm_scoped_groups,
    tech_manager_team_ids,
    technical_sales_team_ids,
    technical_sales_users_for_teams,
)


class FunnelFilterForm(forms.Form):
    """Form for filtering funnel entries on dashboard"""
    stage = forms.ChoiceField(
        choices=[('', 'All Stages')] + SalesFunnel.FUNNEL_STAGES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    brand = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-sm',
            'placeholder': 'Type brand (e.g. Cisco, IBM, Dell)',
            'autocomplete': 'off',
            'list': 'brandSuggestions',
        })
    )
    salesperson = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    group = forms.ModelChoiceField(
        queryset=Group.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    team = forms.ModelChoiceField(
        queryset=Team.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    min_amount = forms.DecimalField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01', 'placeholder': '₱0.00'})
    )
    
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control form-control-sm'
        })
    )
    
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control form-control-sm'
        })
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        qs = User.objects.filter(role='salesperson', is_active=True)
        group_qs = Group.objects.none()
        team_qs = Team.objects.none()
        if user:
            if user.role == 'salesperson':
                qs = User.objects.filter(id=user.id)
                try:
                    team_qs = Team.objects.filter(id=user.team_membership.group.team_id)
                except Exception:
                    team_qs = Team.objects.none()
            elif user.role == 'supervisor':
                groups = Group.objects.filter(supervisor=user)
                group_qs = groups
                salespeople_ids = TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)
                qs = User.objects.filter(id__in=salespeople_ids)
                team_qs = Team.objects.filter(id__in=groups.values_list('team_id', flat=True).distinct())
            elif user.role == 'teamlead':
                teamlead_groups = Group.objects.filter(teamlead=user)
                group_qs = teamlead_groups
                salespeople_ids = TeamMembership.objects.filter(group__in=teamlead_groups).values_list('user_id', flat=True)
                qs = User.objects.filter(id__in=salespeople_ids)
                team_qs = Team.objects.filter(id__in=teamlead_groups.values_list('team_id', flat=True).distinct())
            elif user.role == 'asm':
                # ASM: scope the Group/Salesperson filter to the groups they handle.
                groups = asm_scoped_groups(user)
                group_qs = groups
                salespeople_ids = TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)
                qs = User.objects.filter(id__in=salespeople_ids)
                team_qs = Team.objects.filter(id__in=groups.values_list('team_id', flat=True).distinct())
            elif user.role == 'sm':
                groups = user.sm_groups.all()
                group_qs = groups
                salespeople_ids = TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)
                qs = User.objects.filter(id__in=salespeople_ids)
                team_qs = Team.objects.filter(id__in=groups.values_list('team_id', flat=True).distinct())
            elif user.role == 'avp':
                teams = Team.objects.filter(avp=user)
                groups = Group.objects.filter(team__in=teams)
                group_qs = groups
                salespeople_ids = TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)
                qs = User.objects.filter(id__in=salespeople_ids)
                team_qs = teams
            elif user.role == 'technical_sales':
                qs = User.objects.filter(id=user.id)
                team_qs = Team.objects.filter(id__in=technical_sales_team_ids(user)).order_by('name')
            elif user.role in ['techmgr', 'asst_techmgr']:
                team_ids = tech_manager_team_ids(user)
                qs = technical_sales_users_for_teams(team_ids)
                team_qs = Team.objects.filter(id__in=team_ids).order_by('name')
            else:
                qs = User.objects.filter(role='salesperson', is_active=True)
                group_qs = Group.objects.all()
                team_qs = Team.objects.all()
        else:
            group_qs = Group.objects.all()
            team_qs = Team.objects.all()

        selected_group_id = None
        if self.is_bound:
            selected_group_id = self.data.get(self.add_prefix('group')) or self.data.get('group')
        else:
            initial_group = self.initial.get('group')
            if hasattr(initial_group, 'pk'):
                selected_group_id = initial_group.pk
            else:
                selected_group_id = initial_group

        if selected_group_id:
            qs = qs.filter(team_membership__group_id=selected_group_id)

        self.fields['group'].queryset = group_qs.select_related('team').distinct().order_by('team__name', 'name')
        self.fields['group'].empty_label = '-- All Groups --'
        self.fields['salesperson'].queryset = qs.order_by('first_name', 'last_name')
        self.fields['salesperson'].empty_label = '-- All Salespeople --'

        # Team filter queryset — derived from visible groups unless explicitly
        # provided above for roles that are scoped by teams rather than groups
        # (Technical Sales / Technical Manager).
        if team_qs.exists():
            self.fields['team'].queryset = team_qs.distinct().order_by('name')
        elif group_qs.exists():
            team_ids = group_qs.values_list('team_id', flat=True).distinct()
            self.fields['team'].queryset = Team.objects.filter(id__in=team_ids).order_by('name')
        else:
            self.fields['team'].queryset = Team.objects.none()
        self.fields['team'].empty_label = '-- All Teams --'


class BulkUpdateStageForm(forms.Form):
    """Form for bulk updating funnel stages"""
    entries = forms.CharField(widget=forms.HiddenInput())
    new_stage = forms.ChoiceField(
        choices=SalesFunnel.FUNNEL_STAGES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
