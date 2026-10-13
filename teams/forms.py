from django import forms
from .models import Team, Group, TeamMembership, SupervisorCommitment, PersonalContribution, AsmPersonalTarget, RoleMonthlyQuota, CompanyAnnualTarget
from users.models import User
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, HTML, Field

class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ['name', 'avp', 'asm', 'tech_manager']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['avp'].queryset = User.objects.filter(role='avp')
        self.fields['asm'].queryset = User.objects.filter(role='asm')
        self.fields['tech_manager'].queryset = User.objects.filter(role__in=['techmgr','asst_techmgr'])
        self.fields['avp'].required = False
        self.fields['asm'].required = False
        self.fields['tech_manager'].required = False
        
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('name', css_class='form-group col-md-4 mb-3'),
                Column('avp', css_class='form-group col-md-4 mb-3'),
                Column('asm', css_class='form-group col-md-4 mb-3'),
            ),
            Row(
                Column('tech_manager', css_class='form-group col-md-6 mb-3'),
            ),
            HTML('<br>'),
            Submit('submit', 'Save Team', css_class='btn btn-primary')
        )

class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ['name', 'team', 'supervisor', 'teamlead', 'sm_managers']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Allow both supervisors and ASMs to be assigned as supervisors
        self.fields['supervisor'].queryset = User.objects.filter(role__in=['supervisor', 'asm'])
        self.fields['supervisor'].help_text = 'Select a supervisor or ASM. For TSG groups, leave supervisor empty — they are managed by the team Technical Manager.'
        self.fields['teamlead'].queryset = User.objects.filter(role='teamlead')
        self.fields['teamlead'].required = False
        # Set the widget BEFORE the queryset: assigning .queryset re-binds the
        # widget's choices via ModelChoiceIterator. If the widget is swapped AFTER
        # the queryset, the fresh widget keeps empty choices and renders no boxes.
        self.fields['sm_managers'].widget = forms.CheckboxSelectMultiple()
        self.fields['sm_managers'].queryset = User.objects.filter(role__in=['sm', 'asm'], is_active=True).order_by('first_name', 'last_name')
        self.fields['sm_managers'].required = False
        self.fields['sm_managers'].help_text = 'Assign one or more Sales Managers (SM/ASM) to oversee this group. A manager can oversee multiple groups within the same team, and will only see the groups assigned here.'
        
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('name', css_class='form-group col-md-6 mb-3'),
                Column('team', css_class='form-group col-md-6 mb-3'),
            ),
            Row(
                Column('supervisor', css_class='form-group col-md-6 mb-3'),
                Column('teamlead', css_class='form-group col-md-6 mb-3'),
            ),
            HTML('<h6 class="mt-2">Sales Manager Assignment</h6>'),
            Field('sm_managers'),
            HTML('<br>'),
            Submit('submit', 'Save Group', css_class='btn btn-primary')
        )

class GroupEditForm(forms.ModelForm):
    # Multi-select field for adding/removing members
    members = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(role='salesperson'),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text='Select salesperson users to add to this group. Users can only be in one group at a time.'
    )
    
    class Meta:
        model = Group
        fields = ['name', 'team', 'supervisor', 'teamlead', 'sm_managers', 'members']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Allow both supervisors and ASMs to be supervisors (matches model constraint)
        self.fields['supervisor'].queryset = User.objects.filter(role__in=['supervisor', 'asm'])
        self.fields['supervisor'].help_text = 'Select a supervisor or ASM. ASMs can act as temporary supervisors until a permanent supervisor is hired.'
        self.fields['teamlead'].queryset = User.objects.filter(role='teamlead')
        self.fields['teamlead'].required = False
        # Set the widget BEFORE the queryset: assigning .queryset re-binds the
        # widget's choices via ModelChoiceIterator. If the widget is swapped AFTER
        # the queryset, the fresh widget keeps empty choices and renders no boxes.
        self.fields['sm_managers'].widget = forms.CheckboxSelectMultiple()
        self.fields['sm_managers'].queryset = User.objects.filter(role__in=['sm', 'asm'], is_active=True).order_by('first_name', 'last_name')
        self.fields['sm_managers'].required = False
        self.fields['sm_managers'].help_text = 'Assign one or more Sales Managers (SM/ASM) to oversee this group. Managers will only see the groups assigned here.'
        
        # Filter available salespeople (exclude those already in other groups)
        if self.instance.pk:
            # For existing groups, include current members and unassigned salespeople
            current_member_ids = list(User.objects.filter(team_membership__group=self.instance).values_list('pk', flat=True))
            unassigned_ids = list(User.objects.filter(
                role='salesperson', 
                team_membership__isnull=True
            ).values_list('pk', flat=True))
            
            # Combine the IDs and create a single queryset
            available_ids = current_member_ids + unassigned_ids
            self.fields['members'].queryset = User.objects.filter(pk__in=available_ids)
            
            # Set initial selection to current members
            self.fields['members'].initial = current_member_ids
        else:
            # For new groups, only show unassigned salespeople
            self.fields['members'].queryset = User.objects.filter(
                role='salesperson', 
                team_membership__isnull=True
            )
        
        self.helper = FormHelper()
        self.helper.layout = Layout(
            HTML('<h5>Group Details</h5>'),
            Row(
                Column('name', css_class='form-group col-md-6 mb-3'),
                Column('team', css_class='form-group col-md-6 mb-3'),
            ),
            Row(
                Column('supervisor', css_class='form-group col-md-6 mb-3'),
                Column('teamlead', css_class='form-group col-md-6 mb-3'),
            ),
            HTML('<h6 class="mt-2">Sales Manager Assignment</h6>'),
            Field('sm_managers'),
            HTML('<h5 class="mt-4">Group Members</h5>'),
            Field('members', css_class='form-check-input'),
            HTML('<br>'),
            Submit('submit', 'Save Group', css_class='btn btn-primary me-2')
        )
    
    def save(self, commit=True):
        group = super().save(commit=commit)
        
        if commit:
            # Handle SM managers M2M — super().save() handles it via ModelForm
            # but we need to call save_m2m if commit=True since we override save()
            if hasattr(self, 'save_m2m'):
                self.save_m2m()

            # Get current members
            current_members = set(TeamMembership.objects.filter(group=group).values_list('user_id', flat=True))
            selected_members = self.cleaned_data.get('members', [])
            selected_member_ids = set(user.pk for user in selected_members)
            
            # Members to remove (in current but not in selected)
            to_remove = current_members - selected_member_ids
            if to_remove:
                TeamMembership.objects.filter(group=group, user_id__in=to_remove).delete()
            
            # Members to add (in selected but not in current)
            to_add = selected_member_ids - current_members
            for user_id in to_add:
                user = User.objects.get(pk=user_id)
                # Remove user from any existing group first (since OneToOneField)
                TeamMembership.objects.filter(user=user).delete()
                # Add to this group
                TeamMembership.objects.create(user=user, group=group)
        
        return group

class TeamMembershipQuotaForm(forms.ModelForm):
    class Meta:
        model = TeamMembership
        fields = ['quota']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field('quota', wrapper_class='mb-3'),
            Submit('submit', 'Update Quota', css_class='btn btn-primary')
        )

class SupervisorCommitmentForm(forms.ModelForm):
    class Meta:
        model = SupervisorCommitment
        fields = ['target_profit', 'notes']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field('target_profit', wrapper_class='mb-3'),
            Field('notes', wrapper_class='mb-3'),
            Submit('submit', 'Save Commitment', css_class='btn btn-primary')
        )

class PersonalContributionForm(forms.ModelForm):
    class Meta:
        model = PersonalContribution
        fields = ['amount', 'notes']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field('amount', wrapper_class='mb-3'),
            Field('notes', wrapper_class='mb-3'),
            Submit('submit', 'Save Contribution', css_class='btn btn-primary')
        )

class AsmPersonalTargetForm(forms.ModelForm):
    class Meta:
        model = AsmPersonalTarget
        fields = ['target_amount', 'notes']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field('target_amount', wrapper_class='mb-3'),
            Field('notes', wrapper_class='mb-3'),
            Submit('submit', 'Save ASM Target', css_class='btn btn-primary')
        )

class RoleMonthlyQuotaForm(forms.ModelForm):
    class Meta:
        model = RoleMonthlyQuota
        fields = ['amount', 'notes']
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field('amount', wrapper_class='mb-3'),
            Field('notes', wrapper_class='mb-3'),
            Submit('submit', 'Save Quota', css_class='btn btn-primary')
        )

class CompanyAnnualTargetForm(forms.ModelForm):
    class Meta:
        model = CompanyAnnualTarget
        fields = ['year', 'amount', 'notes']
        labels = {
            'year': 'Fiscal Year',
            'amount': 'Annual Profit Target (₱)',
        }
        help_texts = {
            'year': 'Fiscal year named by the year it ends in — e.g. 2026 = Dec 1 2025 to Nov 30 2026.',
        }
        widgets = {
            'year': forms.NumberInput(attrs={'class': 'form-control', 'min': 2000, 'step': 1}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('year', css_class='form-group col-md-4 mb-3'),
                Column('amount', css_class='form-group col-md-8 mb-3'),
            ),
            Field('notes', wrapper_class='mb-3'),
            Submit('submit', 'Save Annual Target', css_class='btn btn-primary')
        )
