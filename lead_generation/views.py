from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum, Avg
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json
import csv
from datetime import datetime, timedelta

from .models import Lead, LeadSource, LeadActivity, ConversionTracking, LeadNurturingCampaign
from .forms import (
    LeadForm, LeadActivityForm, ConversionForm, MarkLostForm, LeadFilterForm,
    LeadSourceForm, LeadSourceCostUpdateForm, BulkLeadActionForm, LeadImportForm
)
from sales_funnel.models import SalesFunnel
from customers.models import Customer
from users.models import User

EXEC_ROLES = {'admin', 'president', 'gm', 'vp'}
LEAD_SOURCE_CREATOR_ROLES = EXEC_ROLES | {'marketing'}
LEAD_SOURCE_MANAGER_ROLES = {'admin', 'marketing'}


@login_required
def lead_dashboard(request):
    """Main lead generation dashboard"""
    
    # Get leads based on user role
    if request.user.role == 'salesperson':
        leads = Lead.objects.filter(assigned_to=request.user, is_active=True)
    elif request.user.role in ['supervisor', 'asm', 'avp']:
        # Get leads from team members by role
        if request.user.role == 'supervisor':
            groups = request.user.managed_groups.all()
        elif request.user.role == 'asm':
            from teams.models import Group
            groups = Group.objects.filter(team__in=request.user.asm_teams.all())
        else:  # avp
            from teams.models import Group, Team
            groups = Group.objects.filter(team__in=Team.objects.filter(avp=request.user))
        team_members = User.objects.filter(team_membership__group__in=groups, role='salesperson')
        leads = Lead.objects.filter(assigned_to__in=team_members, is_active=True)
    else:
        # Admins and executives see all leads
        leads = Lead.objects.filter(is_active=True)
    
    # Calculate dashboard statistics
    total_leads = leads.count()
    new_leads = leads.filter(status='new').count()
    lost_leads = leads.filter(status='lost').count()
    hot_leads = leads.filter(Q(priority='hot') | Q(lead_score__gte=80)).count()
    
    # Conversion statistics
    converted_leads = leads.filter(status='converted').count()
    conversion_rate = (converted_leads / total_leads * 100) if total_leads > 0 else 0
    
    # Recent activity
    recent_activities = LeadActivity.objects.filter(
        lead__in=leads,
        created_at__gte=timezone.now() - timedelta(days=7)
    ).order_by('-created_at')[:10]
    
    # Leads requiring follow-up
    follow_up_leads = leads.filter(
        next_follow_up_date__lte=timezone.now(),
        status__in=['contacted', 'qualified', 'proposal_sent']
    ).order_by('next_follow_up_date')[:5]
    
    # Top performing sources
    source_stats = LeadSource.objects.annotate(
        lead_count=Count('leads'),
        conversion_count=Count('leads', filter=Q(leads__status='converted'))
    ).filter(lead_count__gt=0).order_by('-conversion_count')[:5]
    
    context = {
        'total_leads': total_leads,
        'new_leads': new_leads,
        'lost_leads': lost_leads,
        'hot_leads': hot_leads,
        'converted_leads': converted_leads,
        'conversion_rate': conversion_rate,
        'recent_activities': recent_activities,
        'follow_up_leads': follow_up_leads,
        'source_stats': source_stats,
    }
    
    return render(request, 'lead_generation/dashboard.html', context)


@login_required
def lead_list(request):
    """List all leads with filtering and pagination"""
    
    # Get base queryset based on user role
    if request.user.role == 'salesperson':
        leads = Lead.objects.filter(assigned_to=request.user, is_active=True)
    elif request.user.role in ['supervisor', 'asm', 'avp']:
        if request.user.role == 'supervisor':
            groups = request.user.managed_groups.all()
        elif request.user.role == 'asm':
            from teams.models import Group
            groups = Group.objects.filter(team__in=request.user.asm_teams.all())
        else:
            from teams.models import Group, Team
            groups = Group.objects.filter(team__in=Team.objects.filter(avp=request.user))
        team_members = User.objects.filter(team_membership__group__in=groups, role='salesperson')
        leads = Lead.objects.filter(assigned_to__in=team_members, is_active=True)
    else:
        leads = Lead.objects.filter(is_active=True)
    
    # Apply filters
    filter_form = LeadFilterForm(request.GET, user=request.user)
    if filter_form.is_valid():
        if filter_form.cleaned_data.get('status'):
            leads = leads.filter(status=filter_form.cleaned_data['status'])
        if filter_form.cleaned_data.get('priority'):
            leads = leads.filter(priority=filter_form.cleaned_data['priority'])
        if filter_form.cleaned_data.get('source'):
            leads = leads.filter(source=filter_form.cleaned_data['source'])
        if filter_form.cleaned_data.get('assigned_to'):
            leads = leads.filter(assigned_to=filter_form.cleaned_data['assigned_to'])
        if filter_form.cleaned_data.get('score_min'):
            leads = leads.filter(lead_score__gte=filter_form.cleaned_data['score_min'])
        if filter_form.cleaned_data.get('score_max'):
            leads = leads.filter(lead_score__lte=filter_form.cleaned_data['score_max'])
        if filter_form.cleaned_data.get('created_from'):
            leads = leads.filter(created_at__date__gte=filter_form.cleaned_data['created_from'])
        if filter_form.cleaned_data.get('created_to'):
            leads = leads.filter(created_at__date__lte=filter_form.cleaned_data['created_to'])
    
    # Apply search
    search_query = request.GET.get('search', '')
    if search_query:
        leads = leads.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(company_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone_number__icontains=search_query)
        )
    
    # Order leads by priority and score
    leads = leads.select_related('source', 'assigned_to').order_by(
        '-priority', '-lead_score', '-created_at'
    )
    
    # Pagination
    paginator = Paginator(leads, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'leads': page_obj,
        'filter_form': filter_form,
        'search_query': search_query,
        'total_count': leads.count(),
    }
    
    return render(request, 'lead_generation/lead_list.html', context)


@login_required
def lead_create(request):
    """Create a new lead"""
    
    if request.method == 'POST':
        form = LeadForm(request.POST, user=request.user)
        if form.is_valid():
            lead = form.save(commit=False)
            lead.created_by = request.user
            
            # Auto-assign to current user if they're a salesperson
            if request.user.role == 'salesperson' and not lead.assigned_to:
                lead.assigned_to = request.user
            
            lead.save()
            
            # Calculate initial lead score
            lead.calculate_lead_score()
            
            # Log creation activity
            LeadActivity.objects.create(
                lead=lead,
                activity_type='note',
                title='Lead Created',
                description=f'New lead created from {lead.source.name}',
                performed_by=request.user,
                outcome='successful'
            )
            
            messages.success(request, f'Lead "{lead.full_name}" created successfully!')
            return redirect('lead_generation:lead_detail', lead_id=lead.id)
    else:
        form = LeadForm(user=request.user)
    
    return render(request, 'lead_generation/lead_form.html', {
        'form': form,
        'title': 'Create New Lead'
    })

@login_required
def lead_import(request):
    created = 0
    errors = []
    if request.method == 'POST':
        form = LeadImportForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            f = form.cleaned_data['file']
            calculate_scores = form.cleaned_data.get('calculate_scores', True)
            default_assigned = form.cleaned_data.get('default_assigned_to')
            file_name = (getattr(f, 'name', '') or '').lower()
            rows = []
            try:
                if file_name.endswith('.xlsx'):
                    from openpyxl import load_workbook
                    wb = load_workbook(f, data_only=True)
                    ws = wb.active
                    all_rows = list(ws.iter_rows(values_only=True))
                    if not all_rows:
                        raise ValueError('The uploaded Excel file is empty.')
                    headers = [str(c).strip() if c is not None else '' for c in all_rows[0]]
                    for r in all_rows[1:]:
                        row = {}
                        for k, v in zip(headers, r):
                            row[k] = '' if v is None else str(v).strip()
                        rows.append(row)
                else:
                    data = f.read().decode('utf-8')
                    reader = csv.DictReader(data.splitlines())
                    rows = list(reader)
            except Exception:
                errors.append('Unable to read the uploaded file. Upload a UTF-8 CSV or an Excel .xlsx file.')
                return render(request, 'lead_generation/lead_import.html', {'form': form, 'created': created, 'errors': errors})

            for i, row in enumerate(rows, start=2):
                try:
                    row_norm = {(k or '').strip().lower(): (v or '').strip() for k, v in (row or {}).items()}
                    first_name = (row_norm.get('first_name') or '').strip()
                    last_name = (row_norm.get('last_name') or '').strip()
                    email = (row_norm.get('email') or '').strip()
                    source_name = (row_norm.get('source') or '').strip()
                    if not first_name or not last_name or not email or not source_name:
                        raise ValueError('first_name, last_name, email, and source are required')
                    source, _ = LeadSource.objects.get_or_create(name=source_name, defaults={'source_type': 'other'})
                    assigned = default_assigned
                    assigned_username = (row_norm.get('assigned_to_username') or '').strip()
                    if assigned_username:
                        try:
                            assigned = User.objects.get(username=assigned_username, role='salesperson', is_active=True)
                        except User.DoesNotExist:
                            assigned = default_assigned or (request.user if request.user.role == 'salesperson' else None)
                    if request.user.role == 'salesperson':
                        assigned = request.user
                    lead = Lead(
                        first_name=first_name,
                        last_name=last_name,
                        email=email,
                        phone_number=(row_norm.get('phone_number') or '').strip(),
                        company_name=(row_norm.get('company_name') or '').strip(),
                        job_title=(row_norm.get('job_title') or '').strip(),
                        address=(row_norm.get('address') or '').strip(),
                        city=(row_norm.get('city') or '').strip(),
                        territory=(row_norm.get('territory') or '').strip(),
                        industry=(row_norm.get('industry') or '').strip(),
                        company_size=(row_norm.get('company_size') or '').strip(),
                        annual_revenue=(row_norm.get('annual_revenue') or '').strip(),
                        status=(row_norm.get('status') or 'new').strip() or 'new',
                        priority=(row_norm.get('priority') or 'medium').strip() or 'medium',
                        source=source,
                        assigned_to=assigned,
                        initial_interest=(row_norm.get('initial_interest') or '').strip(),
                        requirements=(row_norm.get('requirements') or '').strip(),
                        budget_range=(row_norm.get('budget_range') or '').strip(),
                        timeline=(row_norm.get('timeline') or '').strip(),
                        notes=(row_norm.get('notes') or '').strip(),
                        created_by=request.user
                    )
                    lead.save()
                    if calculate_scores:
                        try:
                            lead.calculate_lead_score()
                        except Exception:
                            pass
                    created += 1
                except Exception as e:
                    errors.append(f'Row {i}: {e}')
            return render(request, 'lead_generation/lead_import.html', {'form': form, 'created': created, 'errors': errors, 'done': True})
    else:
        form = LeadImportForm(user=request.user)
    return render(request, 'lead_generation/lead_import.html', {'form': form})

@login_required
def lead_import_template(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="leads_import_template.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'first_name','last_name','email','phone_number','company_name','job_title',
        'address','city','territory','industry','company_size','annual_revenue',
        'status','priority','source','assigned_to_username','initial_interest',
        'requirements','budget_range','timeline','notes'
    ])
    writer.writerow([
        'Juan','Dela Cruz','juan.dela@example.com','+63-2-555-1234','ABC Corp','IT Manager',
        '123 Ayala Ave','Makati','makati','technology','51-200','10m_50m',
        'new','medium','Website','salesuser1','Interested in network upgrade',
        'Needs 10 switches','100k_500k','short_term',''
    ])
    return response

@login_required
def lead_detail(request, lead_id):
    """View lead details with activities and conversion options"""
    
    lead = get_object_or_404(Lead, id=lead_id)
    
    # Check permissions
    if request.user.role == 'salesperson' and lead.assigned_to != request.user:
        messages.error(request, 'You can only view leads assigned to you.')
        return redirect('lead_generation:lead_list')
    elif request.user.role in ['supervisor', 'asm', 'avp']:
        # Check if lead is assigned to a team member within the viewer's scope
        if request.user.role == 'supervisor':
            groups = request.user.managed_groups.all()
        elif request.user.role == 'asm':
            from teams.models import Group
            groups = Group.objects.filter(team__in=request.user.asm_teams.all())
        else:
            from teams.models import Group, Team
            groups = Group.objects.filter(team__in=Team.objects.filter(avp=request.user))
        team_members = User.objects.filter(team_membership__group__in=groups, role='salesperson')
        if lead.assigned_to not in team_members:
            messages.error(request, 'You can only view leads from your team.')
            return redirect('lead_generation:lead_list')
    
    # Get recent activities
    activities = lead.activities.select_related('performed_by').order_by('-created_at')
    
    # Forms for quick actions
    activity_form = LeadActivityForm()
    conversion_form = ConversionForm()
    mark_lost_form = MarkLostForm()
    
    context = {
        'lead': lead,
        'activities': activities,
        'activity_form': activity_form,
        'conversion_form': conversion_form,
        'mark_lost_form': mark_lost_form,
        'can_edit': request.user.role != 'salesperson' or lead.assigned_to == request.user,
        'can_convert': lead.can_convert_to_customer,
        'can_mark_lost': lead.status not in ['converted', 'lost'],
    }
    
    return render(request, 'lead_generation/lead_detail.html', context)


@login_required
def my_leads(request):
    """Show leads assigned to current salesperson"""
    
    if request.user.role != 'salesperson':
        return redirect('lead_generation:lead_list')
    
    leads = Lead.objects.filter(
        assigned_to=request.user,
        is_active=True
    ).select_related('source').order_by('-priority', '-lead_score', '-created_at')
    
    # Statistics for current salesperson
    total_leads = leads.count()
    qualified_leads = leads.filter(is_qualified=True).count()
    converted_leads = leads.filter(status='converted').count()
    conversion_rate = (converted_leads / total_leads * 100) if total_leads > 0 else 0
    
    context = {
        'leads': leads,
        'total_leads': total_leads,
        'qualified_leads': qualified_leads,
        'converted_leads': converted_leads,
        'conversion_rate': conversion_rate,
    }
    
    return render(request, 'lead_generation/my_leads.html', context)


@login_required
def lead_edit(request, lead_id):
    """Edit an existing lead"""
    
    lead = get_object_or_404(Lead, id=lead_id)
    
    # Check permissions
    if request.user.role == 'salesperson' and lead.assigned_to != request.user:
        messages.error(request, 'You can only edit leads assigned to you.')
        return redirect('lead_generation:lead_list')
    
    if request.method == 'POST':
        form = LeadForm(request.POST, instance=lead, user=request.user)
        if form.is_valid():
            updated_lead = form.save()
            
            # Recalculate lead score
            updated_lead.calculate_lead_score()
            
            messages.success(request, f'Lead "{updated_lead.full_name}" updated successfully!')
            return redirect('lead_generation:lead_detail', lead_id=updated_lead.id)
    else:
        form = LeadForm(instance=lead, user=request.user)
    
    return render(request, 'lead_generation/lead_form.html', {
        'form': form,
        'lead': lead,
        'title': f'Edit Lead: {lead.full_name}'
    })


@login_required
def convert_lead(request, lead_id):
    """Convert lead to customer"""
    
    lead = get_object_or_404(Lead, id=lead_id)
    
    # Check permissions
    if request.user.role == 'salesperson' and lead.assigned_to != request.user:
        messages.error(request, 'You can only convert leads assigned to you.')
        return redirect('lead_generation:lead_detail', lead_id=lead.id)
    
    # Check if already converted
    if lead.converted_to_customer:
        messages.warning(request, 'This lead has already been converted to a customer.')
        return redirect('lead_generation:lead_detail', lead_id=lead.id)
    
    if request.method == 'POST':
        form = ConversionForm(request.POST)
        if form.is_valid():
            create_sales_funnel_entry = form.cleaned_data.get('create_sales_funnel_entry')
            assigned_salesperson = lead.assigned_to or (request.user if request.user.role == 'salesperson' else None)

            if create_sales_funnel_entry and not assigned_salesperson:
                form.add_error('create_sales_funnel_entry', 'Assign the lead to a salesperson before creating a sales funnel entry.')
            else:
                customer = lead.convert_to_customer(
                    salesperson=assigned_salesperson,
                    conversion_value=form.cleaned_data.get('conversion_value'),
                    notes=form.cleaned_data.get('notes', ''),
                    create_sales_funnel_entry=create_sales_funnel_entry,
                    sales_funnel_stage=form.cleaned_data.get('sales_funnel_stage'),
                    converted_by=request.user,
                )

                messages.success(request, f'Lead successfully converted to customer: {customer.company_name}')
                return redirect('customer_detail', pk=customer.id)
    else:
        form = ConversionForm(initial={
            'conversion_value': lead.conversion_value,
            'notes': lead.notes,
        })
    
    return render(request, 'lead_generation/convert_lead.html', {
        'lead': lead,
        'form': form,
    })


@login_required
@require_http_methods(["POST"])
def mark_lead_lost(request, lead_id):
    """Mark a lead as lost with reason and notes."""
    lead = get_object_or_404(Lead, id=lead_id)

    if request.user.role == 'salesperson' and lead.assigned_to != request.user:
        messages.error(request, 'You can only update leads assigned to you.')
        return redirect('lead_generation:lead_detail', lead_id=lead.id)

    if lead.status == 'converted':
        messages.error(request, 'Converted leads cannot be marked as lost.')
        return redirect('lead_generation:lead_detail', lead_id=lead.id)

    if lead.status == 'lost':
        messages.info(request, 'This lead is already marked as lost.')
        return redirect('lead_generation:lead_detail', lead_id=lead.id)

    form = MarkLostForm(request.POST)
    if form.is_valid():
        lead.mark_as_lost(
            user=request.user,
            reason=form.cleaned_data['reason'],
            notes=form.cleaned_data.get('notes', ''),
        )
        messages.success(request, f'Lead "{lead.full_name}" marked as lost.')
    else:
        messages.error(request, 'Unable to mark lead as lost. Please complete the required fields.')

    return redirect('lead_generation:lead_detail', lead_id=lead.id)


@login_required
@require_http_methods(["POST"])
def add_lead_activity(request, lead_id):
    """Add activity to a lead (AJAX)"""
    
    lead = get_object_or_404(Lead, id=lead_id)
    
    # Check permissions
    if request.user.role == 'salesperson' and lead.assigned_to != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    form = LeadActivityForm(request.POST)
    if form.is_valid():
        activity = form.save(commit=False)
        activity.lead = lead
        activity.performed_by = request.user
        activity.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Activity logged successfully'
        })
    else:
        return JsonResponse({'error': 'Invalid form data', 'errors': form.errors}, status=400)


@login_required
def lead_sources(request):
    """Manage lead sources"""
    
    sources = LeadSource.objects.annotate(
        lead_count=Count('leads'),
        conversion_count=Count('leads', filter=Q(leads__status='converted'))
    ).order_by('name')
    
    return render(request, 'lead_generation/source_list.html', {
        'sources': sources,
        'can_create_sources': request.user.role in LEAD_SOURCE_CREATOR_ROLES,
        'can_manage_sources': request.user.role in LEAD_SOURCE_MANAGER_ROLES,
    })


@login_required
def lead_source_create(request):
    """Create new lead source"""
    
    if request.user.role not in LEAD_SOURCE_CREATOR_ROLES:
        messages.error(request, 'You do not have permission to create lead sources.')
        return redirect('lead_generation:lead_sources')
    
    if request.method == 'POST':
        form = LeadSourceForm(request.POST)
        if form.is_valid():
            source = form.save()
            messages.success(request, f'Lead source "{source.name}" created successfully!')
            return redirect('lead_generation:lead_sources')
    else:
        form = LeadSourceForm()
    
    return render(request, 'lead_generation/source_form.html', {
        'form': form,
        'title': 'Create Lead Source'
    })


@login_required
def lead_source_edit(request, source_id):
    """Edit a lead source; only Marketing and Admin can change existing sources."""
    if request.user.role not in LEAD_SOURCE_MANAGER_ROLES:
        return HttpResponseForbidden('You do not have permission to edit lead sources.')

    source = get_object_or_404(LeadSource, id=source_id)
    if request.method == 'POST':
        form = LeadSourceForm(request.POST, instance=source)
        if form.is_valid():
            form.save()
            messages.success(request, f'Lead source "{source.name}" updated successfully.')
            return redirect('lead_generation:lead_sources')
    else:
        form = LeadSourceForm(instance=source)

    return render(request, 'lead_generation/source_form.html', {
        'form': form,
        'title': f'Edit Lead Source: {source.name}',
    })


@login_required
@require_http_methods(["POST"])
def lead_source_update_cost(request, source_id):
    """Update one lead source's cost per lead for Marketing/Admin users."""
    if request.user.role not in LEAD_SOURCE_MANAGER_ROLES:
        return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)

    source = get_object_or_404(LeadSource, id=source_id)
    form = LeadSourceCostUpdateForm(request.POST)
    if not form.is_valid():
        error = form.errors.get('cost_per_lead', ['Enter a valid non-negative amount.'])[0]
        return JsonResponse({'success': False, 'error': error}, status=400)

    source.cost_per_lead = form.cleaned_data['cost_per_lead']
    source.save(update_fields=['cost_per_lead'])
    return JsonResponse({
        'success': True,
        'cost_per_lead': f'{source.cost_per_lead:.2f}',
        'display': f'₱{source.cost_per_lead:,.2f}',
    })


@login_required
def analytics_dashboard(request):
    """Lead generation analytics and reporting"""
    
    # Date range filtering (Default: Last 30 days)
    end_date = timezone.now()
    start_date = (end_date - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Leads QuerySet
    leads = Lead.objects.filter(created_at__gte=start_date)
    
    # 1. Lead Performance Overview
    total_leads = leads.count()
    converted_leads = leads.filter(status='converted').count()
    conversion_rate = (converted_leads / total_leads * 100) if total_leads > 0 else 0
    avg_lead_score = leads.aggregate(Avg('lead_score'))['lead_score__avg'] or 0
    
    # 2. Leads by Status
    status_distribution = list(leads.values('status').annotate(count=Count('id')).order_by('-count'))
    # Map status codes to labels for display
    status_labels = dict(Lead.STATUS_CHOICES)
    for item in status_distribution:
        item['label'] = status_labels.get(item['status'], item['status'])
        
    # 3. Leads by Source
    source_distribution = list(leads.values('source__name').annotate(count=Count('id')).order_by('-count'))
    
    # 4. Leads by Salesperson (Top 10)
    salesperson_performance = list(leads.exclude(assigned_to=None).values(
        'assigned_to__username', 
        'assigned_to__first_name', 
        'assigned_to__last_name'
    ).annotate(
        total=Count('id'),
        converted=Count('id', filter=Q(status='converted')),
        avg_score=Avg('lead_score')
    ).order_by('-total')[:10])
    
    for sp in salesperson_performance:
        name = f"{sp['assigned_to__first_name']} {sp['assigned_to__last_name']}".strip()
        sp['name'] = name if name else sp['assigned_to__username']
        sp['conversion_rate'] = (sp['converted'] / sp['total'] * 100) if sp['total'] > 0 else 0

    # 5. Timeline Data (Daily creation)
    # Using python to group by date to ensure compatibility with all DB backends (SQLite/MySQL)
    timeline_data = {}
    current_day = start_date
    while current_day <= end_date:
        date_str = current_day.strftime('%Y-%m-%d')
        timeline_data[date_str] = 0
        current_day += timedelta(days=1)
        
    leads_timeline = leads.values('created_at__date').annotate(count=Count('id'))
    for entry in leads_timeline:
        date_str = entry['created_at__date'].strftime('%Y-%m-%d')
        if date_str in timeline_data:
            timeline_data[date_str] = entry['count']
            
    context = {
        'page_title': 'Lead Analytics',
        'total_leads': total_leads,
        'converted_leads': converted_leads,
        'conversion_rate': conversion_rate,
        'avg_lead_score': avg_lead_score,
        'status_distribution_json': json.dumps(status_distribution),
        'source_distribution_json': json.dumps(source_distribution),
        'salesperson_performance_json': json.dumps(salesperson_performance),
        'timeline_labels_json': json.dumps(list(timeline_data.keys())),
        'timeline_values_json': json.dumps(list(timeline_data.values())),
        'start_date': start_date,
        'end_date': end_date,
    }
    
    return render(request, 'lead_generation/analytics.html', context)


@login_required
def hot_leads(request):
    """Show all hot leads for quick access"""
    
    # Get hot leads based on user role
    if request.user.role == 'salesperson':
        leads = Lead.objects.filter(
            assigned_to=request.user,
            is_active=True
        )
    elif request.user.role in ['supervisor', 'asm', 'avp']:
        team_members = User.objects.filter(
            team_membership__group__in=request.user.managed_groups.all(),
            role='salesperson'
        )
        leads = Lead.objects.filter(
            assigned_to__in=team_members,
            is_active=True
        )
    else:
        leads = Lead.objects.filter(is_active=True)
    
    # Filter for hot leads
    hot_leads = leads.filter(
        Q(priority='hot') | Q(lead_score__gte=80)
    ).select_related('source', 'assigned_to').order_by('-lead_score', '-created_at')
    
    context = {
        'hot_leads': hot_leads,
        'total_count': hot_leads.count()
    }
    
    return render(request, 'lead_generation/hot_leads.html', context)


@login_required
def update_lead_status(request, lead_id):
    """Quick status update for leads"""
    
    lead = get_object_or_404(Lead, id=lead_id)
    
    # Check permissions
    if request.user.role == 'salesperson' and lead.assigned_to != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    return JsonResponse({'success': True, 'message': 'Status updated'})


@login_required
def lead_export(request):
    """Export leads to CSV"""
    
    return HttpResponse('Export feature coming soon!', content_type='text/plain')
