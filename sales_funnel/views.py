from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Sum, Count, F
from django.utils import timezone
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.conf import settings
from .models import SalesFunnel
from .forms import SalesFunnelForm, FunnelFilterForm, BulkUpdateStageForm
from users.models import User
from teams.models import Team, Group, TeamMembership, asm_scoped_groups
from customers.models import Customer, CustomerHistory
import csv
import logging
from io import TextIOWrapper, StringIO
from decimal import Decimal
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _sum_entry_retail(entries):
    return sum((entry.display_retail for entry in entries), Decimal('0.00'))


def _sum_entry_profit(entries):
    return sum((entry.profit for entry in entries), Decimal('0.00'))


def _send_avp_notes_notification(request, entry, old_notes, new_notes):
    """
    Send an email notification to the AE (salesperson) and their group supervisor
    when an AVP updates the notes field on a funnel entry.

    Failures are silenced — the save has already succeeded by the time this runs.
    """
    updater = request.user

    # Collect recipients: AE + supervisor of AE's group
    recipients = {}  # email -> display name

    ae = entry.salesperson
    if ae and ae.email:
        recipients[ae.email] = ae.get_full_name() or ae.username

    try:
        membership = TeamMembership.objects.select_related(
            'group__supervisor'
        ).get(user=ae)
        supervisor = membership.group.supervisor if membership.group else None
        if supervisor and supervisor.email and supervisor != ae:
            recipients[supervisor.email] = supervisor.get_full_name() or supervisor.username
    except (TeamMembership.DoesNotExist, AttributeError):
        pass

    if not recipients:
        logger.warning(
            'avp_notes_notification: no recipients resolved for funnel entry %s', entry.pk
        )
        return

    # Build the absolute URL to the funnel entry detail page
    try:
        from django.urls import reverse
        funnel_path = reverse('sales_funnel:entry_detail', kwargs={'entry_id': entry.pk})
        funnel_url = request.build_absolute_uri(funnel_path)
    except Exception:
        funnel_url = request.build_absolute_uri('/')

    updater_role_display = dict(updater.ROLE_CHOICES).get(updater.role, updater.role.title())
    salesperson_name = ae.get_full_name() or ae.username if ae else '—'

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@microimageph.com')
    subject = (
        f'[CRM] Funnel Notes Updated by {updater.get_full_name() or updater.username} '
        f'— {entry.company_name}'
    )

    for email_addr, display_name in recipients.items():
        try:
            body = render_to_string(
                'sales_funnel/email/avp_notes_notification.txt',
                {
                    'recipient_name': display_name,
                    'updater_name': updater.get_full_name() or updater.username,
                    'updater_role': updater_role_display,
                    'entry': entry,
                    'salesperson_name': salesperson_name,
                    'old_notes': old_notes.strip() if old_notes else '',
                    'new_notes': new_notes.strip(),
                    'funnel_url': funnel_url,
                    'company_name': getattr(settings, 'COMPANY_NAME', 'Micro Image International Corp.'),
                    'company_address': getattr(settings, 'COMPANY_ADDRESS', ''),
                    'company_website': getattr(settings, 'COMPANY_WEBSITE_URL', ''),
                },
            )
            EmailMessage(
                subject=subject,
                body=body,
                from_email=from_email,
                to=[email_addr],
            ).send(fail_silently=False)
            logger.info(
                'avp_notes_notification: sent to %s for funnel entry %s', email_addr, entry.pk
            )
        except Exception as exc:
            # Never let email failure break the user's save action
            logger.error(
                'avp_notes_notification: failed to send to %s for funnel entry %s — %s',
                email_addr, entry.pk, exc,
            )


def can_access_funnel(user):
    """Check if user can access sales funnel features"""
    return user.role in ['salesperson', 'supervisor', 'teamlead', 'asm', 'sm', 'avp', 'admin', 'president', 'gm', 'vp']

def is_salesperson(user):
    return user.role == 'salesperson'

def is_manager(user):
    return user.role in ['supervisor', 'teamlead', 'asm', 'sm', 'avp', 'admin', 'president', 'gm', 'vp']

def is_exec_admin(user):
    return user.role in ['admin', 'president', 'gm', 'vp']

def can_add_entry(user):
    return user.role in ['salesperson', 'supervisor', 'asm', 'sm', 'avp']

def can_import_entries(user):
    return user.role in ['salesperson', 'supervisor', 'asm', 'sm', 'avp', 'admin']


# Maps the funnel stage DB codes to their display color name used across the UI
# (Pink/Yellow/Green/Blue) plus the hex/badge color. Single source of truth so
# the dashboard KPI card and the per-stage pages stay consistent.
FUNNEL_STAGE_META = {
    'quoted':   {'label': 'PINK',   'name': 'Newly Quoted',   'hex': '#e91e63', 'badge': 'danger'},
    'closable': {'label': 'YELLOW', 'name': 'Closable Deals', 'hex': '#ffc107', 'badge': 'warning'},
    'project':  {'label': 'GREEN',  'name': 'Green Funnel',   'hex': '#28a745', 'badge': 'success'},
    'services': {'label': 'BLUE',   'name': 'Blue Funnel',    'hex': '#007bff', 'badge': 'primary'},
}


def visible_funnel_entries(user):
    """
    Return the active, open funnel entries a user is allowed to see, applying the
    same role-based scoping used by the dashboard. Centralized here so the
    dashboard and the per-stage pages share one source of truth for visibility.
    """
    base = SalesFunnel.objects.filter(is_active=True, is_closed=False)
    scope = funnel_scope_q(user)
    return base if scope is None else base.filter(scope)


def funnel_scope_q(user):
    """
    Return a Q() expressing which salespeople's funnel entries `user` may see,
    or None for executives/admins (unrestricted). Shared by visible_funnel_entries
    and by the removed-entries review page so one role map drives both. Does NOT
    itself filter on is_active/is_closed — callers decide the lifecycle slice.
    """
    if user.role == 'salesperson':
        return Q(salesperson=user)
    if user.role == 'supervisor':
        groups = Group.objects.filter(supervisor=user)
        sp_ids = TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)
        return Q(salesperson_id__in=sp_ids) | Q(salesperson=user)
    if user.role == 'teamlead':
        groups = Group.objects.filter(teamlead=user)
        sp_ids = TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)
        return Q(salesperson_id__in=sp_ids)
    if user.role == 'asm':
        groups = asm_scoped_groups(user)
        sp_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
        supervisor_ids = list(groups.filter(supervisor__isnull=False).values_list('supervisor_id', flat=True))
        return Q(salesperson_id__in=sp_ids + supervisor_ids) | Q(salesperson=user)
    if user.role == 'sm':
        groups = user.sm_groups.all()
        sp_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
        supervisor_ids = list(Group.objects.filter(id__in=groups.values_list('id', flat=True), supervisor__isnull=False).values_list('supervisor_id', flat=True))
        return Q(salesperson_id__in=sp_ids + supervisor_ids) | Q(salesperson=user)
    if user.role == 'avp':
        teams = Team.objects.filter(avp=user)
        groups = Group.objects.filter(team__in=teams)
        sp_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
        asm_ids = list(teams.exclude(asm__isnull=True).values_list('asm_id', flat=True))
        supervisor_ids = list(Group.objects.filter(team__in=teams, supervisor__isnull=False).values_list('supervisor_id', flat=True))
        return Q(salesperson_id__in=sp_ids + asm_ids + supervisor_ids) | Q(salesperson=user)
    # Executives and admins can see all entries
    return None


@login_required
@user_passes_test(can_access_funnel)
def funnel_stage_detail(request, stage):
    """
    Focused page listing all visible entries for a single funnel stage
    (PINK/YELLOW/GREEN/BLUE). Reached by clicking a stage in the dashboard's
    Pipeline Stages card. Includes a Back to Dashboard button.
    """
    if stage not in FUNNEL_STAGE_META:
        messages.error(request, 'Unknown funnel stage.')
        return redirect('sales_funnel:dashboard')

    user = request.user
    entries = list(
        visible_funnel_entries(user)
        .filter(stage=stage)
        .select_related('salesperson', 'customer', 'proposal')
        .order_by('-date_created')
    )

    meta = FUNNEL_STAGE_META[stage]
    context = {
        'stage': stage,
        'stage_meta': meta,
        'stage_display': dict(SalesFunnel.FUNNEL_STAGES).get(stage, meta['name']),
        'entries': entries,
        'entry_count': len(entries),
        'total_retail': _sum_entry_retail(entries),
        'total_profit': _sum_entry_profit(entries),
        'can_add': can_add_entry(user),
        'can_edit_all': user.role in ['admin', 'supervisor', 'asm', 'sm', 'avp'],
        # Everyone listed here is already within the user's scope (the list is
        # built from visible_funnel_entries), so a role check is sufficient to
        # offer Remove. Closed deals are excluded from this list already.
        'can_remove': user.role in [
            'salesperson', 'supervisor', 'teamlead', 'asm', 'sm', 'avp',
            'admin', 'president', 'gm', 'vp',
        ],
    }
    return render(request, 'sales_funnel/stage_detail.html', context)


@login_required
@user_passes_test(can_access_funnel)
def funnel_dashboard(request):
    """Main dashboard view for sales funnel"""
    user = request.user
    view_mode = request.GET.get('view', 'card')
    
    # Get funnel entries based on user role
    if user.role == 'salesperson':
        funnel_entries = SalesFunnel.objects.filter(
            salesperson=user,
            is_active=True,
            is_closed=False
        )
    elif user.role == 'supervisor':
        # Supervisor can see entries from their groups
        groups = Group.objects.filter(supervisor=user)
        salespeople_ids = TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)
        funnel_entries = SalesFunnel.objects.filter(
            Q(salesperson_id__in=salespeople_ids) | Q(salesperson=user),
            is_active=True,
            is_closed=False
        )
    elif user.role == 'teamlead':
        # Teamlead can see entries from their assigned group
        teamlead_groups = Group.objects.filter(teamlead=user)
        salespeople_ids = TeamMembership.objects.filter(group__in=teamlead_groups).values_list('user_id', flat=True)
        funnel_entries = SalesFunnel.objects.filter(
            salesperson_id__in=salespeople_ids,
            is_active=True,
            is_closed=False
        )
    elif user.role == 'asm':
        # ASM sees entries only from the groups they handle (sm_managers), with a
        # whole-team fallback when none are assigned. Mirrors Proposals/Monitoring.
        groups = asm_scoped_groups(user)
        salespeople_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
        supervisor_ids = list(groups.filter(supervisor__isnull=False).values_list('supervisor_id', flat=True))
        visible_ids = salespeople_ids + supervisor_ids
        funnel_entries = SalesFunnel.objects.filter(
            Q(salesperson_id__in=visible_ids) | Q(salesperson=user),
            is_active=True,
            is_closed=False
        )
    elif user.role == 'sm':
        # SM sees only their assigned groups
        groups = user.sm_groups.all()
        salespeople_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
        supervisor_ids = list(Group.objects.filter(id__in=groups.values_list('id', flat=True), supervisor__isnull=False).values_list('supervisor_id', flat=True))
        visible_ids = salespeople_ids + supervisor_ids
        funnel_entries = SalesFunnel.objects.filter(
            Q(salesperson_id__in=visible_ids) | Q(salesperson=user),
            is_active=True,
            is_closed=False
        )
    elif user.role == 'avp':
        # AVP can see entries from their teams
        teams = Team.objects.filter(avp=user)
        groups = Group.objects.filter(team__in=teams)
        salespeople_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
        asm_ids = list(teams.exclude(asm__isnull=True).values_list('asm_id', flat=True))
        supervisor_ids = list(Group.objects.filter(team__in=teams, supervisor__isnull=False).values_list('supervisor_id', flat=True))
        visible_ids = salespeople_ids + asm_ids + supervisor_ids
        funnel_entries = SalesFunnel.objects.filter(
            Q(salesperson_id__in=visible_ids) | Q(salesperson=user),
            is_active=True,
            is_closed=False
        )
    else:
        # Executives and admins can see all entries
        funnel_entries = SalesFunnel.objects.filter(
            is_active=True,
            is_closed=False
        )
    accessible_entries = funnel_entries
    
    # Apply filters if provided
    filter_form = FunnelFilterForm(request.GET, user=user)
    if filter_form.is_valid():
        stage = filter_form.cleaned_data.get('stage')
        brand = filter_form.cleaned_data.get('brand')
        salesperson = filter_form.cleaned_data.get('salesperson')
        group = filter_form.cleaned_data.get('group')
        team = filter_form.cleaned_data.get('team')
        min_amount = filter_form.cleaned_data.get('min_amount')
        date_from = filter_form.cleaned_data.get('date_from')
        date_to = filter_form.cleaned_data.get('date_to')
        
        if stage:
            funnel_entries = funnel_entries.filter(stage=stage)
        if brand:
            funnel_entries = funnel_entries.filter(brand__icontains=brand.strip())
        if team:
            funnel_entries = funnel_entries.filter(salesperson__team_membership__group__team=team)
        if group:
            funnel_entries = funnel_entries.filter(salesperson__team_membership__group=group)
        if salesperson:
            funnel_entries = funnel_entries.filter(salesperson=salesperson)
        if min_amount is not None:
            funnel_entries = funnel_entries.filter(retail__gte=min_amount)
        if date_from:
            funnel_entries = funnel_entries.filter(date_created__gte=date_from)
        if date_to:
            funnel_entries = funnel_entries.filter(date_created__lte=date_to)

    today = timezone.localdate()
    
    # Organize entries by stage (show all active entries in each stage)
    quoted_entries = list(
        funnel_entries
        .filter(stage='quoted')
        .select_related('salesperson', 'customer', 'proposal')
    )
    closable_entries = list(funnel_entries.filter(stage='closable').select_related('salesperson', 'customer', 'proposal'))
    project_entries = list(funnel_entries.filter(stage='project').select_related('salesperson', 'customer', 'proposal'))
    services_entries = list(funnel_entries.filter(stage='services').select_related('salesperson', 'customer', 'proposal'))
    all_visible_entries = quoted_entries + closable_entries + project_entries + services_entries
    
    # Get closed deals statistics based on same user role logic
    if user.role == 'salesperson':
        closed_deals = SalesFunnel.objects.filter(salesperson=user, is_closed=True)
    elif user.role == 'supervisor':
        groups = Group.objects.filter(supervisor=user)
        salespeople_ids = TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)
        closed_deals = SalesFunnel.objects.filter(Q(salesperson_id__in=salespeople_ids) | Q(salesperson=user), is_closed=True)
    elif user.role == 'teamlead':
        teamlead_groups = Group.objects.filter(teamlead=user)
        salespeople_ids = TeamMembership.objects.filter(group__in=teamlead_groups).values_list('user_id', flat=True)
        closed_deals = SalesFunnel.objects.filter(salesperson_id__in=salespeople_ids, is_closed=True)
    elif user.role == 'asm':
        groups = asm_scoped_groups(user)
        salespeople_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
        supervisor_ids = list(groups.filter(supervisor__isnull=False).values_list('supervisor_id', flat=True))
        visible_ids = salespeople_ids + supervisor_ids
        closed_deals = SalesFunnel.objects.filter(Q(salesperson_id__in=visible_ids) | Q(salesperson=user), is_closed=True)
    elif user.role == 'sm':
        groups = user.sm_groups.all()
        salespeople_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
        supervisor_ids = list(Group.objects.filter(id__in=groups.values_list('id', flat=True), supervisor__isnull=False).values_list('supervisor_id', flat=True))
        visible_ids = salespeople_ids + supervisor_ids
        closed_deals = SalesFunnel.objects.filter(Q(salesperson_id__in=visible_ids) | Q(salesperson=user), is_closed=True)
    elif user.role == 'avp':
        teams = Team.objects.filter(avp=user)
        groups = Group.objects.filter(team__in=teams)
        salespeople_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
        asm_ids = list(teams.exclude(asm__isnull=True).values_list('asm_id', flat=True))
        supervisor_ids = list(Group.objects.filter(team__in=teams, supervisor__isnull=False).values_list('supervisor_id', flat=True))
        visible_ids = salespeople_ids + asm_ids + supervisor_ids
        closed_deals = SalesFunnel.objects.filter(Q(salesperson_id__in=visible_ids) | Q(salesperson=user), is_closed=True)
    else:
        closed_deals = SalesFunnel.objects.filter(is_closed=True)
    
    # Calculate won/lost statistics
    won_deals = closed_deals.filter(deal_outcome='won')
    lost_deals = closed_deals.filter(deal_outcome='lost')
    total_closed = closed_deals.count()
    
    won_stats = {
        'count': won_deals.count(),
        'total_value': won_deals.aggregate(Sum('retail'))['retail__sum'] or 0,
    }
    lost_stats = {
        'count': lost_deals.count(),
        'total_value': lost_deals.aggregate(Sum('retail'))['retail__sum'] or 0,
    }
    win_rate = (won_stats['count'] / total_closed * 100) if total_closed > 0 else 0
    
    # Calculate statistics
    stats = {
        'total_entries': len(all_visible_entries),
        'total_value': _sum_entry_retail(all_visible_entries),
        'total_profit': _sum_entry_profit(all_visible_entries),
        'quoted_count': len(quoted_entries),
        'closable_count': len(closable_entries),
        'project_count': len(project_entries),
        'services_count': len(services_entries),
        # Add won/lost stats
        'won_count': won_stats['count'],
        'lost_count': lost_stats['count'],
        'total_closed': total_closed,
        'win_rate': win_rate,
        'won_value': won_stats['total_value'],
        'lost_value': lost_stats['total_value'],
    }
    # Stage totals for table view
    stage_totals = {
        'quoted': {
            'retail': _sum_entry_retail(quoted_entries),
            'profit': _sum_entry_profit(quoted_entries),
        },
        'closable': {
            'retail': _sum_entry_retail(closable_entries),
            'profit': _sum_entry_profit(closable_entries),
        },
        'project': {
            'retail': _sum_entry_retail(project_entries),
            'profit': _sum_entry_profit(project_entries),
        },
        'services': {
            'retail': _sum_entry_retail(services_entries),
            'profit': _sum_entry_profit(services_entries),
        },
    }
    brand_suggestions = list(
        accessible_entries.exclude(brand__isnull=True)
        .exclude(brand='')
        .order_by('brand')
        .values_list('brand', flat=True)
        .distinct()
    )
    
    context = {
        'quoted_entries': quoted_entries,
        'closable_entries': closable_entries,
        'project_entries': project_entries,
        'services_entries': services_entries,
        'stats': stats,
        'stage_totals': stage_totals,
        'filter_form': filter_form,
        'can_add': can_add_entry(user),
        'can_import': can_import_entries(user),
        'can_edit_all': user.role in ['admin', 'supervisor', 'asm', 'sm', 'avp'],
        'view_mode': view_mode,
        'show_actions': view_mode != 'table',
        'brand_suggestions': brand_suggestions,
    }
    
    return render(request, 'sales_funnel/dashboard.html', context)


@login_required
@user_passes_test(is_manager)
def export_funnel_report(request):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    user = request.user
    if user.role == 'salesperson':
        return redirect('sales_funnel:dashboard')

    if user.role == 'supervisor':
        groups = Group.objects.filter(supervisor=user)
        salespeople_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
        qs = SalesFunnel.objects.filter(Q(salesperson_id__in=salespeople_ids) | Q(salesperson=user), is_active=True, is_closed=False)
    elif user.role == 'teamlead':
        teamlead_groups = Group.objects.filter(teamlead=user)
        salespeople_ids = TeamMembership.objects.filter(group__in=teamlead_groups).values_list('user_id', flat=True)
        qs = SalesFunnel.objects.filter(salesperson_id__in=salespeople_ids, is_active=True, is_closed=False)
    elif user.role == 'asm':
        groups = asm_scoped_groups(user)
        salespeople_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
        supervisor_ids = list(groups.filter(supervisor__isnull=False).values_list('supervisor_id', flat=True))
        visible_ids = salespeople_ids + supervisor_ids
        qs = SalesFunnel.objects.filter(Q(salesperson_id__in=visible_ids) | Q(salesperson=user), is_active=True, is_closed=False)
    elif user.role == 'sm':
        groups = user.sm_groups.all()
        salespeople_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
        supervisor_ids = list(Group.objects.filter(id__in=groups.values_list('id', flat=True), supervisor__isnull=False).values_list('supervisor_id', flat=True))
        visible_ids = salespeople_ids + supervisor_ids
        qs = SalesFunnel.objects.filter(Q(salesperson_id__in=visible_ids) | Q(salesperson=user), is_active=True, is_closed=False)
    elif user.role == 'avp':
        teams = Team.objects.filter(avp=user)
        groups = Group.objects.filter(team__in=teams)
        salespeople_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
        asm_ids = list(teams.exclude(asm__isnull=True).values_list('asm_id', flat=True))
        supervisor_ids = list(Group.objects.filter(team__in=teams, supervisor__isnull=False).values_list('supervisor_id', flat=True))
        visible_ids = salespeople_ids + asm_ids + supervisor_ids
        qs = SalesFunnel.objects.filter(Q(salesperson_id__in=visible_ids) | Q(salesperson=user), is_active=True, is_closed=False)
    else:
        qs = SalesFunnel.objects.filter(is_active=True, is_closed=False)

    form = FunnelFilterForm(request.GET, user=user)
    if form.is_valid():
        stage = form.cleaned_data.get('stage')
        brand = form.cleaned_data.get('brand')
        salesperson = form.cleaned_data.get('salesperson')
        group = form.cleaned_data.get('group')
        team = form.cleaned_data.get('team')
        min_amount = form.cleaned_data.get('min_amount')
        date_from = form.cleaned_data.get('date_from')
        date_to = form.cleaned_data.get('date_to')
        if stage:
            qs = qs.filter(stage=stage)
        if brand:
            qs = qs.filter(brand__icontains=brand.strip())
        if team:
            qs = qs.filter(salesperson__team_membership__group__team=team)
        if group:
            qs = qs.filter(salesperson__team_membership__group=group)
        if salesperson:
            qs = qs.filter(salesperson=salesperson)
        if min_amount is not None:
            qs = qs.filter(retail__gte=min_amount)
        if date_from:
            qs = qs.filter(date_created__gte=date_from)
        if date_to:
            qs = qs.filter(date_created__lte=date_to)

    # Build Excel workbook grouped by stage
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    STAGE_ORDER = [
        ('quoted', 'PINK', 'FF69B4'),
        ('closable', 'YELLOW', 'FFD700'),
        ('project', 'GREEN', '28A745'),
        ('services', 'BLUE', '007BFF'),
    ]

    header_font = Font(bold=True, color='FFFFFF', size=10)
    header_border = Border(
        bottom=Side(style='thin'),
        top=Side(style='thin'),
        left=Side(style='thin'),
        right=Side(style='thin'),
    )
    data_border = Border(
        bottom=Side(style='thin', color='DDDDDD'),
        left=Side(style='thin', color='DDDDDD'),
        right=Side(style='thin', color='DDDDDD'),
    )
    headers = ['GROUP', 'AE', 'COMPANY NAME', 'REQUIREMENT', 'PRODUCT COST', 'REVENUE', 'PROFIT', '% MARGIN', 'OPPORTUNITY STARTED', 'PROBABILITY OF WIN', 'TIME FRAME', 'WEEK ACTIVITY REPORT']

    for stage_key, stage_label, stage_color in STAGE_ORDER:
        entries = list(qs.filter(stage=stage_key).select_related('salesperson', 'salesperson__team_membership__group', 'customer').order_by('-date_created'))
        ws = wb.create_sheet(title=stage_label)

        # Header row
        header_fill = PatternFill(start_color=stage_color, end_color=stage_color, fill_type='solid')
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = header_border

        # Data rows
        for row_idx, e in enumerate(entries, 2):
            # Resolve group name
            group_name = ''
            try:
                if e.salesperson and hasattr(e.salesperson, 'team_membership'):
                    group_name = e.salesperson.team_membership.group.name
            except Exception:
                pass
            # AE initials (3-letter code)
            am_initials = ''
            if e.salesperson:
                am_initials = (e.salesperson.initials or '').upper()
                if not am_initials:
                    parts = [e.salesperson.first_name, e.salesperson.last_name]
                    am_initials = ''.join((p[:1] or '').upper() for p in parts if p)
                    if not am_initials:
                        am_initials = e.salesperson.username[:3].upper()
            # % Margin calculation
            revenue = float(e.retail)
            profit = float(e.profit)
            margin_pct = (profit / revenue * 100) if revenue > 0 else 0

            row_data = [
                group_name,
                am_initials,
                e.company_name,
                e.requirement_description or '',
                float(e.cost),
                revenue,
                profit,
                round(margin_pct, 2),
                e.date_created.strftime('%Y-%m-%d'),
                e.probability,
                e.expected_close_date.strftime('%Y-%m-%d') if e.expected_close_date else '',
                e.notes or '',
            ]
            for col_idx, val in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.border = data_border
                if col_idx in (5, 6, 7):  # Currency columns (Product Cost, Revenue, Profit)
                    cell.number_format = '#,##0.00'
                elif col_idx == 8:  # % Margin
                    cell.number_format = '0.00"%"'

        # Auto-width columns
        for col_idx in range(1, len(headers) + 1):
            col_letter = get_column_letter(col_idx)
            max_len = len(headers[col_idx - 1])
            for row in ws.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx):
                for cell in row:
                    if cell.value:
                        max_len = max(max_len, min(len(str(cell.value)), 40))
            ws.column_dimensions[col_letter].width = max_len + 3

        # Summary row
        if entries:
            summary_row = len(entries) + 2
            ws.cell(row=summary_row, column=4, value='TOTAL').font = Font(bold=True)
            ws.cell(row=summary_row, column=5, value=float(sum(e.cost for e in entries))).font = Font(bold=True)
            ws.cell(row=summary_row, column=5).number_format = '#,##0.00'
            ws.cell(row=summary_row, column=6, value=float(sum(e.retail for e in entries))).font = Font(bold=True)
            ws.cell(row=summary_row, column=6).number_format = '#,##0.00'
            ws.cell(row=summary_row, column=7, value=float(sum(e.profit for e in entries))).font = Font(bold=True)
            ws.cell(row=summary_row, column=7).number_format = '#,##0.00'
            # Average margin
            total_revenue = float(sum(e.retail for e in entries))
            total_profit = float(sum(e.profit for e in entries))
            avg_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
            ws.cell(row=summary_row, column=8, value=round(avg_margin, 2)).font = Font(bold=True)
            ws.cell(row=summary_row, column=8).number_format = '0.00"%"'

    # If no sheets were created (all empty), add a placeholder
    if not wb.sheetnames:
        ws = wb.create_sheet(title='No Data')
        ws.cell(row=1, column=1, value='No funnel entries found for the selected filters.')

    # Write response
    from io import BytesIO
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    # Build filename with team name prefix
    team_name_prefix = ''
    if user.role == 'avp':
        team_obj = user.managed_teams.first()
        if team_obj:
            team_name_prefix = team_obj.name.upper().replace(' ', '_') + '_'
    elif user.role == 'asm':
        team_obj = user.asm_teams.first()
        if team_obj:
            team_name_prefix = team_obj.name.upper().replace(' ', '_') + '_'
    elif user.role == 'sm':
        sm_group = user.sm_groups.select_related('team').first()
        if sm_group and sm_group.team:
            team_name_prefix = sm_group.team.name.upper().replace(' ', '_') + '_'
    elif user.role == 'supervisor':
        sup_group = user.managed_groups.select_related('team').first()
        if sup_group and sup_group.team:
            team_name_prefix = sup_group.team.name.upper().replace(' ', '_') + '_'

    filename = f"{team_name_prefix}SALES_FUNNEL_{timezone.now().strftime('%Y%m%d')}.xlsx"
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@user_passes_test(can_add_entry)
def add_funnel_entry(request):
    """Add a new funnel entry (salesperson only)"""
    if request.method == 'POST':
        form = SalesFunnelForm(request.POST, user=request.user)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.salesperson = request.user
            entry.save()
            messages.success(request, 'Funnel entry added successfully!')
            return redirect('sales_funnel:dashboard')
    else:
        form = SalesFunnelForm(user=request.user)
    
    return render(request, 'sales_funnel/add_entry.html', {'form': form})


@login_required
@user_passes_test(can_add_entry)
def add_test_funnel_entry(request):
    """
    Add a throwaway TEST funnel entry. Identical to add_funnel_entry but marks
    the entry `is_test=True`, so it is the only kind that can later be deleted.
    Use this for trying things out / demos without polluting real pipeline.
    """
    if request.method == 'POST':
        form = SalesFunnelForm(request.POST, user=request.user)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.salesperson = request.user
            entry.is_test = True
            entry.save()
            messages.success(request, 'TEST funnel entry added. It can be safely deleted later.')
            return redirect('sales_funnel:dashboard')
    else:
        form = SalesFunnelForm(user=request.user)

    return render(request, 'sales_funnel/add_entry.html', {'form': form, 'is_test': True})


@login_required
@user_passes_test(can_access_funnel)
def funnel_entry_detail(request, entry_id):
    """Read-only detail view for a funnel entry."""
    entry = get_object_or_404(SalesFunnel, id=entry_id)

    if request.user.role == 'salesperson' and entry.salesperson != request.user:
        messages.error(request, 'You can only view your own funnel entries.')
        return redirect('sales_funnel:dashboard')

    return render(request, 'sales_funnel/entry_detail.html', {
        'entry': entry,
    })


@login_required
@user_passes_test(can_access_funnel)
def edit_funnel_entry(request, entry_id):
    """Edit a funnel entry"""
    entry = get_object_or_404(SalesFunnel, id=entry_id)
    
    # Check permissions
    if request.user.role == 'salesperson' and entry.salesperson != request.user:
        messages.error(request, 'You can only edit your own funnel entries.')
        return redirect('sales_funnel:dashboard')
    
    if request.method == 'POST':
        # Capture the notes value before the form overwrites it
        old_notes = entry.notes or ''

        form = SalesFunnelForm(request.POST, instance=entry, user=request.user)
        if form.is_valid():
            updated_entry = form.save()
            new_notes = updated_entry.notes or ''

            # Notify AE and supervisor when an AVP updates the notes field
            if (
                request.user.role == 'avp'
                and new_notes.strip() != old_notes.strip()
                and new_notes.strip()
            ):
                _send_avp_notes_notification(request, updated_entry, old_notes, new_notes)

            messages.success(request, 'Funnel entry updated successfully!')
            return redirect('sales_funnel:dashboard')
    else:
        form = SalesFunnelForm(instance=entry, user=request.user)
    
    return render(request, 'sales_funnel/edit_entry.html', {
        'form': form,
        'entry': entry
    })


@login_required
@user_passes_test(can_access_funnel)
def delete_funnel_entry(request, entry_id):
    """
    Delete a funnel entry.

    HARD RULE: only entries explicitly flagged as TEST (`is_test=True`) may be
    deleted. Real pipeline — including won/lost deals and proposal-linked
    entries — must never be destroyed (that would silently erase revenue from
    every report). Real deals are ended with Close (Won/Lost) instead.
    See docs/SALES_FUNNEL_DOCUMENTATION.md.
    """
    entry = get_object_or_404(SalesFunnel, id=entry_id)

    # Only test entries can be deleted, no matter the role.
    if not entry.is_test:
        messages.error(
            request,
            'Only TEST funnel entries can be deleted. For a real deal, use '
            'Close (Won/Lost) — deleting would remove it from reports permanently.'
        )
        return redirect('sales_funnel:dashboard')

    # A salesperson may only delete their own (test) entries.
    if request.user.role == 'salesperson' and entry.salesperson != request.user:
        messages.error(request, 'You can only delete your own funnel entries.')
        return redirect('sales_funnel:dashboard')

    if request.method == 'POST':
        company_name = entry.company_name
        entry.delete()
        messages.success(request, f'Test funnel entry for "{company_name}" deleted successfully!')

    return redirect('sales_funnel:dashboard')


def _can_manage_funnel_entry(user, entry):
    """
    May `user` remove/restore this funnel entry? A salesperson may act on their
    own entries; managers/execs on any entry within their scope. Mirrors the
    role scoping used elsewhere in the funnel.
    """
    if user.role == 'salesperson':
        return entry.salesperson_id == user.id
    scope = funnel_scope_q(user)
    if scope is None:  # exec / admin — unrestricted
        return True
    return SalesFunnel.objects.filter(scope, pk=entry.pk).exists()


@login_required
@user_passes_test(can_access_funnel)
def remove_funnel_entry(request, entry_id):
    """
    Soft-delete ("remove") a real funnel entry from the active pipeline.

    Unlike delete (test entries only), this never destroys the row. It records a
    REQUIRED reason, who removed it, and when, and sets is_active=False so the
    entry drops out of the dashboard/pipeline totals. The archived entry — with
    its reason — stays available for supervisor review and can be restored.
    Use when a customer changes requirements and a fresh proposal is coming, so
    the stale entry doesn't inflate the pipeline.
    """
    entry = get_object_or_404(SalesFunnel, id=entry_id)

    if not _can_manage_funnel_entry(request.user, entry):
        messages.error(request, 'You can only remove funnel entries within your scope.')
        return redirect('sales_funnel:dashboard')

    if entry.is_closed:
        messages.error(request, 'Closed (won/lost) deals cannot be removed — they are part of your results history.')
        return redirect('sales_funnel:dashboard')

    if not entry.is_active:
        messages.info(request, 'That entry has already been removed from the pipeline.')
        return redirect('sales_funnel:dashboard')

    if request.method == 'POST':
        reason = (request.POST.get('remove_reason') or '').strip()
        if not reason:
            messages.error(
                request,
                'Please provide a reason for removing this entry so your supervisor can review it.'
            )
            return redirect('sales_funnel:dashboard')

        entry.is_active = False
        entry.removed_reason = reason
        entry.removed_at = timezone.now()
        entry.removed_by = request.user
        entry.save(update_fields=['is_active', 'removed_reason', 'removed_at', 'removed_by', 'updated_at'])

        # Leave an audit trail on the customer timeline for supervisor review.
        if entry.customer:
            try:
                CustomerHistory.objects.create(
                    customer=entry.customer,
                    action='funnel_entry_removed',
                    description=(
                        f'Funnel entry for {entry.company_name} '
                        f'(SRP ₱{entry.retail}, stage {entry.get_stage_display()}) '
                        f'removed from the pipeline. Reason: {reason}'
                    ),
                    changed_by=request.user,
                    salesperson_at_time=entry.salesperson,
                    old_value={'is_active': True, 'stage': entry.stage},
                    new_value={
                        'is_active': False,
                        'removed_reason': reason,
                        'removed_at': entry.removed_at.isoformat(),
                        'removed_by': request.user.get_full_name() or request.user.username,
                    },
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                )
            except Exception:
                pass

        messages.success(
            request,
            f'Entry for "{entry.company_name}" removed from the pipeline. '
            'It is kept for review and can be restored.'
        )

    return redirect('sales_funnel:dashboard')


@login_required
@user_passes_test(can_access_funnel)
def restore_funnel_entry(request, entry_id):
    """Restore a previously removed (archived) funnel entry back into the pipeline."""
    entry = get_object_or_404(SalesFunnel, id=entry_id)

    if not _can_manage_funnel_entry(request.user, entry):
        messages.error(request, 'You can only restore funnel entries within your scope.')
        return redirect('sales_funnel:removed_entries')

    if entry.is_active:
        messages.info(request, 'That entry is already active in the pipeline.')
        return redirect('sales_funnel:removed_entries')

    if request.method == 'POST':
        prior_reason = entry.removed_reason
        entry.is_active = True
        entry.removed_reason = ''
        entry.removed_at = None
        entry.removed_by = None
        entry.save(update_fields=['is_active', 'removed_reason', 'removed_at', 'removed_by', 'updated_at'])

        if entry.customer:
            try:
                CustomerHistory.objects.create(
                    customer=entry.customer,
                    action='funnel_entry_restored',
                    description=(
                        f'Funnel entry for {entry.company_name} restored to the pipeline '
                        f'(was removed with reason: {prior_reason or "n/a"}).'
                    ),
                    changed_by=request.user,
                    salesperson_at_time=entry.salesperson,
                    old_value={'is_active': False},
                    new_value={'is_active': True},
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                )
            except Exception:
                pass

        messages.success(request, f'Entry for "{entry.company_name}" restored to the pipeline.')

    return redirect('sales_funnel:removed_entries')


@login_required
@user_passes_test(can_access_funnel)
def removed_funnel_entries(request):
    """
    Review page listing funnel entries that were removed (soft-deleted) from the
    pipeline, with the reason, who removed them, and when. Role-scoped: a
    salesperson sees their own; supervisors/ASM/SM/AVP see their teams'; execs
    see all. Supervisors and above can restore an entry.
    """
    user = request.user
    scope = funnel_scope_q(user)
    qs = SalesFunnel.objects.filter(is_active=False, is_closed=False)
    if scope is not None:
        qs = qs.filter(scope)
    entries = list(
        qs.select_related('salesperson', 'customer', 'removed_by', 'proposal')
        .order_by('-removed_at', '-updated_at')
    )

    can_restore = user.role in ['supervisor', 'teamlead', 'asm', 'sm', 'avp', 'admin', 'president', 'gm', 'vp']

    return render(request, 'sales_funnel/removed_entries.html', {
        'entries': entries,
        'entry_count': len(entries),
        'can_restore': can_restore,
    })


@login_required
@user_passes_test(can_access_funnel)
def update_entry_stage(request, entry_id):
    """AJAX endpoint to update funnel entry stage"""
    if request.method == 'POST':
        entry = get_object_or_404(SalesFunnel, id=entry_id)
        
        # Check permissions
        if request.user.role == 'salesperson' and entry.salesperson != request.user:
            return JsonResponse({
                'success': False,
                'message': 'Permission denied'
            })
        
        new_stage = request.POST.get('stage')
        if new_stage in ['quoted', 'closable', 'project', 'services']:
            if new_stage in ['project', 'services']:
                # Enforce threshold-based classification
                from decimal import Decimal
                threshold = Decimal('500000')
                entry.stage = 'project' if entry.retail >= threshold else 'services'
            else:
                entry.stage = new_stage
            entry.save()
            
            return JsonResponse({
                'success': True,
                'message': f'Entry moved to {entry.get_stage_display()}',
                'stage': entry.stage,
                'stage_display': entry.get_stage_display(),
                'stage_color': entry.stage_color
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Invalid stage'
            })
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})


@login_required
@user_passes_test(can_access_funnel)
def update_entry_notes(request, entry_id):
    """AJAX endpoint to update funnel entry notes inline."""
    if request.method == 'POST':
        entry = get_object_or_404(SalesFunnel, id=entry_id)

        # Permission: salesperson can only edit their own entries;
        # managers/execs can edit any entry they can see.
        if request.user.role == 'salesperson' and entry.salesperson != request.user:
            return JsonResponse({'success': False, 'message': 'Permission denied'}, status=403)

        import json
        try:
            body = json.loads(request.body)
            new_notes = body.get('notes', '').strip()
        except (json.JSONDecodeError, AttributeError):
            new_notes = request.POST.get('notes', '').strip()

        entry.notes = new_notes
        entry.save(update_fields=['notes'])

        return JsonResponse({
            'success': True,
            'notes': entry.notes,
            'notes_truncated': (entry.notes[:12] + '...') if len(entry.notes) > 15 else entry.notes,
        })

    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)


@login_required
@user_passes_test(can_access_funnel)
def close_entry(request, entry_id):
    """Mark a funnel entry as closed (won or lost)"""
    entry = get_object_or_404(SalesFunnel, id=entry_id)
    
    # Check permissions
    if request.user.role == 'salesperson' and entry.salesperson != request.user:
        messages.error(request, 'You can only close your own funnel entries.')
        return redirect('sales_funnel:dashboard')
    
    if request.method == 'POST':
        won = request.POST.get('won') == 'true'
        lost_reason = (request.POST.get('lost_reason') or '').strip()

        # A lost deal must carry a reason — it's how the rest of the team learns
        # what went wrong. Won deals don't need one.
        if not won and not lost_reason:
            messages.error(
                request,
                'Please provide a reason when marking a deal as LOST so the team can learn from it.'
            )
            return redirect('sales_funnel:dashboard')

        old_outcome = entry.deal_outcome
        entry.is_closed = True
        entry.deal_outcome = 'won' if won else 'lost'
        entry.closed_date = timezone.now().date()
        entry.lost_reason = lost_reason if not won else ''
        closing_note = f"Closed on {entry.closed_date} - {'WON' if won else 'LOST'}"
        if not won and lost_reason:
            closing_note += f"\nReason lost: {lost_reason}"
        entry.notes = f"{entry.notes}\n\n{closing_note}".strip()
        entry.save()
        
        # Log purchase to customer history
        if entry.customer:
            action = 'deal_won' if won else 'deal_lost'
            profit = (entry.retail or Decimal('0')) - (entry.cost or Decimal('0'))
            description = f"Deal {('WON' if won else 'LOST')} for {entry.company_name} (SRP ₱{entry.retail}, Cost ₱{entry.cost}, Profit ₱{profit})."
            if not won and lost_reason:
                description += f" Reason lost: {lost_reason}"
            new_value = {
                'deal_outcome': entry.deal_outcome,
                'is_closed': True,
                'closed_date': str(entry.closed_date),
                'retail': float(entry.retail or 0),
                'cost': float(entry.cost or 0),
                'profit': float(profit),
            }
            if not won and lost_reason:
                new_value['lost_reason'] = lost_reason
            try:
                CustomerHistory.objects.create(
                    customer=entry.customer,
                    action=action,
                    description=description,
                    changed_by=request.user,
                    salesperson_at_time=entry.salesperson,
                    old_value={
                        'deal_outcome': old_outcome,
                        'is_closed': False,
                    },
                    new_value=new_value,
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
                )
            except Exception:
                pass
        
        status = 'won' if won else 'lost'
        messages.success(request, f'Deal for "{entry.company_name}" marked as {status}!')
    
    return redirect('sales_funnel:dashboard')


@login_required
@user_passes_test(can_access_funnel)
def deals_history(request):
    """View to show comprehensive won/lost deal statistics"""
    user = request.user
    outcome = request.GET.get('outcome', '').strip().lower()
    
    # Get closed deals based on user role - similar logic to funnel_dashboard
    if user.role == 'salesperson':
        closed_deals = SalesFunnel.objects.filter(
            salesperson=user,
            is_closed=True
        )
    elif user.role == 'supervisor':
        groups = Group.objects.filter(supervisor=user)
        salespeople_ids = TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)
        closed_deals = SalesFunnel.objects.filter(
            Q(salesperson_id__in=salespeople_ids) | Q(salesperson=user),
            is_closed=True
        )
    elif user.role == 'teamlead':
        teamlead_groups = Group.objects.filter(teamlead=user)
        salespeople_ids = TeamMembership.objects.filter(group__in=teamlead_groups).values_list('user_id', flat=True)
        closed_deals = SalesFunnel.objects.filter(
            salesperson_id__in=salespeople_ids,
            is_closed=True
        )
    elif user.role == 'asm':
        groups = asm_scoped_groups(user)
        salespeople_ids = TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)
        closed_deals = SalesFunnel.objects.filter(
            Q(salesperson_id__in=salespeople_ids) | Q(salesperson=user),
            is_closed=True
        )
    elif user.role == 'sm':
        groups = user.sm_groups.all()
        salespeople_ids = TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)
        closed_deals = SalesFunnel.objects.filter(
            Q(salesperson_id__in=salespeople_ids) | Q(salesperson=user),
            is_closed=True
        )
    elif user.role == 'avp':
        teams = Team.objects.filter(avp=user)
        groups = Group.objects.filter(team__in=teams)
        salespeople_ids = TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)
        closed_deals = SalesFunnel.objects.filter(
            Q(salesperson_id__in=salespeople_ids) | Q(salesperson=user),
            is_closed=True
        )
    else:
        # Executives and admins can see all closed deals
        closed_deals = SalesFunnel.objects.filter(is_closed=True)
    
    # Apply date filters if provided
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if date_from:
        closed_deals = closed_deals.filter(closed_date__gte=date_from)
    if date_to:
        closed_deals = closed_deals.filter(closed_date__lte=date_to)
    
    # Separate won and lost deals
    won_deals = closed_deals.filter(deal_outcome='won').select_related('salesperson', 'customer')
    lost_deals = closed_deals.filter(deal_outcome='lost').select_related('salesperson', 'customer')
    
    if outcome == 'won':
        won_deals = won_deals
        lost_deals = lost_deals.none()
    elif outcome == 'lost':
        lost_deals = lost_deals
        won_deals = won_deals.none()
    
    # Calculate overall statistics
    won_stats = {
        'count': won_deals.count(),
        'total_value': won_deals.aggregate(Sum('retail'))['retail__sum'] or 0,
        'total_cost': won_deals.aggregate(Sum('cost'))['cost__sum'] or 0,
    }
    won_stats['total_profit'] = won_stats['total_value'] - won_stats['total_cost']
    
    # Calculate profit margin percentage
    if won_stats['total_value'] > 0:
        won_stats['profit_margin'] = (won_stats['total_profit'] / won_stats['total_value']) * 100
    else:
        won_stats['profit_margin'] = 0
    
    lost_stats = {
        'count': lost_deals.count(),
        'total_value': lost_deals.aggregate(Sum('retail'))['retail__sum'] or 0,
        'total_cost': lost_deals.aggregate(Sum('cost'))['cost__sum'] or 0,
    }
    lost_stats['total_profit'] = lost_stats['total_value'] - lost_stats['total_cost']
    
    # Calculate win rate and averages
    total_closed = won_stats['count'] + lost_stats['count']
    win_rate = (won_stats['count'] / total_closed * 100) if total_closed > 0 else 0
    
    # Calculate average values
    total_value_all = won_stats['total_value'] + lost_stats['total_value']
    average_deal_value = (total_value_all / total_closed) if total_closed > 0 else 0
    average_won_deal = (won_stats['total_value'] / won_stats['count']) if won_stats['count'] > 0 else 0
    
    # Get top performing salespeople (if user can see multiple salespeople)
    top_salespeople = []
    if user.role in ['supervisor', 'teamlead', 'asm', 'avp', 'admin', 'president', 'gm', 'vp']:
        from django.db.models import Count as DbCount
        salespeople_stats = closed_deals.values(
            'salesperson__username',
            'salesperson__first_name', 
            'salesperson__last_name'
        ).annotate(
            won_count=DbCount('id', filter=Q(deal_outcome='won')),
            lost_count=DbCount('id', filter=Q(deal_outcome='lost')),
            total_won_value=Sum('retail', filter=Q(deal_outcome='won')),
            total_lost_value=Sum('retail', filter=Q(deal_outcome='lost'))
        ).order_by('-won_count')[:10]
        
        # Calculate win rate for each salesperson
        top_salespeople = []
        for sp in salespeople_stats:
            total_deals = sp['won_count'] + sp['lost_count']
            win_rate = (sp['won_count'] / total_deals * 100) if total_deals > 0 else 0
            sp['total_deals'] = total_deals
            sp['win_rate'] = win_rate
            sp['total_won_value'] = sp['total_won_value'] or 0
            sp['total_lost_value'] = sp['total_lost_value'] or 0
            top_salespeople.append(sp)
    
    # Recent won and lost deals
    recent_won = won_deals.order_by('-closed_date')[:10]
    recent_lost = lost_deals.order_by('-closed_date')[:10]
    
    context = {
        'won_stats': won_stats,
        'lost_stats': lost_stats,
        'win_rate': win_rate,
        'total_closed': total_closed,
        'recent_won': recent_won,
        'recent_lost': recent_lost,
        'top_salespeople': top_salespeople,
        'date_from': date_from,
        'date_to': date_to,
        'outcome': outcome,
        'can_see_all_salespeople': user.role in ['supervisor', 'teamlead', 'asm', 'avp', 'admin', 'president', 'gm', 'vp'],
        'average_deal_value': average_deal_value,
        'average_won_deal': average_won_deal,
    }
    
    return render(request, 'sales_funnel/deals_history.html', context)


@login_required
@user_passes_test(can_import_entries)
def import_funnel_entries(request):
    if request.method == 'POST':
        # Determine target salesperson
        target_salesperson = None
        if request.user.role == 'salesperson':
            target_salesperson = request.user
        else:
            sp_id = request.POST.get('salesperson')
            if not sp_id:
                messages.error(request, 'Please select a salesperson to assign imported entries.')
                return redirect('sales_funnel:import_entries')
            try:
                sp = User.objects.get(id=sp_id, is_active=True)
            except User.DoesNotExist:
                messages.error(request, 'Selected salesperson not found or inactive.')
                return redirect('sales_funnel:import_entries')
            # Scope validation for supervisor/asm/avp
            allowed_ids = []
            if request.user.role == 'supervisor':
                groups = Group.objects.filter(supervisor=request.user)
                allowed_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)) + [request.user.id]
            elif request.user.role == 'asm':
                groups = asm_scoped_groups(request.user)
                sp_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
                supervisor_ids = list(groups.filter(supervisor__isnull=False).values_list('supervisor_id', flat=True))
                allowed_ids = sp_ids + supervisor_ids + [request.user.id]
            elif request.user.role == 'sm':
                groups = request.user.sm_groups.all()
                sp_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
                supervisor_ids = list(Group.objects.filter(id__in=groups.values_list('id', flat=True), supervisor__isnull=False).values_list('supervisor_id', flat=True))
                allowed_ids = sp_ids + supervisor_ids + [request.user.id]
            elif request.user.role == 'avp':
                teams = Team.objects.filter(avp=request.user)
                groups = Group.objects.filter(team__in=teams)
                sp_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
                asm_ids = list(teams.exclude(asm__isnull=True).values_list('asm_id', flat=True))
                supervisor_ids = list(Group.objects.filter(team__in=teams, supervisor__isnull=False).values_list('supervisor_id', flat=True))
                allowed_ids = sp_ids + asm_ids + supervisor_ids + [request.user.id]
            elif request.user.role == 'admin':
                allowed_ids = [sp.id]
            if allowed_ids and sp.id not in allowed_ids:
                messages.error(request, 'You can only import entries for salespeople in your scope.')
                return redirect('sales_funnel:import_entries')
            target_salesperson = sp
        file = request.FILES.get('csv_file')
        if not file:
            messages.error(request, 'Please select a CSV file to upload.')
            return redirect('sales_funnel:import_entries')

        try:
            # Read file content
            content = file.read()
            
            # Try decoding with different encodings
            decoded_file = None
            encoding_error = None
            
            for encoding in ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1', 'utf-16']:
                try:
                    decoded_file = content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if decoded_file is None:
                messages.error(request, 'Unable to read the CSV file. Unsupported encoding.')
                return redirect('sales_funnel:import_entries')

            # Use StringIO for CSV reading
            csv_file = StringIO(decoded_file)
            
            # Try to sniff dialect (delimiter)
            try:
                sample = decoded_file[:4096]
                dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
            except csv.Error:
                dialect = 'excel'
            
            csv_file.seek(0)
            
            # Read headers to normalize them
            reader = csv.reader(csv_file, dialect=dialect)
            try:
                headers = next(reader)
            except StopIteration:
                messages.error(request, 'CSV file is empty.')
                return redirect('sales_funnel:import_entries')
                
            # Normalize headers: strip whitespace and convert to lowercase
            normalized_headers = [h.strip().lower() for h in headers]
            
            # Create DictReader with normalized headers
            rows = csv.DictReader(csv_file, fieldnames=normalized_headers, dialect=dialect)
        except Exception as e:
            messages.error(request, f'Error reading CSV file: {str(e)}')
            return redirect('sales_funnel:import_entries')

        stage_map = {
            'newly quoted': 'quoted',
            'quoted': 'quoted',
            'closable this month': 'closable',
            'closable': 'closable',
            'project based': 'project',
            'project': 'project',
            'services': 'services',
        }

        def parse_date(value):
            if not value:
                return None
            for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%b %d %Y'):
                try:
                    return datetime.strptime(value.strip(), fmt).date()
                except Exception:
                    continue
            return None

        def parse_decimal(value):
            if value is None:
                return Decimal('0')
            s = str(value).replace('₱', '').replace(',', '').replace(' ', '').strip()
            if not s:
                return Decimal('0')
            try:
                return Decimal(s)
            except Exception:
                return None

        created = 0
        failed = 0
        errors = []

        for idx, row in enumerate(rows, start=1):
            getv = lambda k: row.get(k.strip().lower())
            date_created = getv('Date Created')
            company_name = getv('Company Name')
            brand_val = getv('Brand')
            requirement_description = getv('Requirement Description')
            cost_val = getv('Cost')
            retail_val = getv('SRP') or getv('Retail')
            stage_val = getv('Stage')
            customer_name = getv('Customer')
            expected_close_date = getv('Expected Close Date')
            probability_val = getv('Probability')
            notes_val = getv('Notes')

            if not all([date_created, company_name, requirement_description, cost_val, retail_val, stage_val]):
                failed += 1
                errors.append(f'Row {idx}: missing required fields')
                continue

            dc = parse_date(date_created)
            if not dc:
                failed += 1
                errors.append(f'Row {idx}: invalid Date Created')
                continue

            cost = parse_decimal(cost_val)
            retail = parse_decimal(retail_val)
            if cost is None or retail is None:
                failed += 1
                errors.append(f'Row {idx}: invalid numeric Cost/SRP')
                continue

            stage_key = str(stage_val).strip().lower()
            stage = stage_map.get(stage_key)
            if stage not in ['quoted', 'closable', 'project', 'services']:
                failed += 1
                errors.append(f'Row {idx}: invalid Stage')
                continue

            prob = 50
            if probability_val not in [None, '']:
                try:
                    val = str(probability_val).replace('%', '').strip()
                    prob = int(float(val))
                except Exception:
                    failed += 1
                    errors.append(f'Row {idx}: invalid Probability')
                    continue
                if prob < 0 or prob > 100:
                    failed += 1
                    errors.append(f'Row {idx}: Probability out of range')
                    continue

            if retail < cost:
                failed += 1
                errors.append(f'Row {idx}: SRP less than Cost')
                continue

            customer_obj = None
            if customer_name:
                customer_obj = Customer.objects.filter(company_name__iexact=customer_name.strip(), is_active=True).first()

            exp_close = parse_date(expected_close_date) if expected_close_date else None

            entry = SalesFunnel(
                date_created=dc,
                company_name=company_name.strip(),
                brand=(str(brand_val).strip() if brand_val else ''),
                requirement_description=str(requirement_description).strip(),
                cost=cost,
                retail=retail,
                stage=('project' if stage in ['project','services'] and retail is not None and retail >= Decimal('500000') else ('services' if stage in ['project','services'] else stage)),
                salesperson=target_salesperson,
                customer=customer_obj,
                expected_close_date=exp_close,
                probability=prob,
                notes=(str(notes_val).strip() if notes_val else ''),
            )

            try:
                entry.save()
                created += 1
            except Exception as e:
                failed += 1
                errors.append(f'Row {idx}: {str(e)[:200]}')

        if created:
            messages.success(request, f'Imported {created} funnel entries.')
        if failed:
            preview = '; '.join(errors[:5])
            if preview:
                messages.warning(request, f'{failed} rows failed. {preview}')
        return redirect('sales_funnel:dashboard')

    # GET: show form; for managers, provide salesperson selector within scope
    available_salespeople = None
    if request.user.role in ['supervisor', 'asm', 'sm', 'avp', 'admin']:
        if request.user.role == 'supervisor':
            groups = Group.objects.filter(supervisor=request.user)
            sp_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)) + [request.user.id]
        elif request.user.role == 'asm':
            groups = asm_scoped_groups(request.user)
            sp_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
            supervisor_ids = list(groups.filter(supervisor__isnull=False).values_list('supervisor_id', flat=True))
            sp_ids = sp_ids + supervisor_ids + [request.user.id]
        elif request.user.role == 'sm':
            groups = request.user.sm_groups.all()
            sp_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
            supervisor_ids = list(Group.objects.filter(id__in=groups.values_list('id', flat=True), supervisor__isnull=False).values_list('supervisor_id', flat=True))
            sp_ids = sp_ids + supervisor_ids + [request.user.id]
        elif request.user.role == 'avp':
            teams = Team.objects.filter(avp=request.user)
            groups = Group.objects.filter(team__in=teams)
            sp_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
            asm_ids = list(teams.exclude(asm__isnull=True).values_list('asm_id', flat=True))
            supervisor_ids = list(Group.objects.filter(team__in=teams, supervisor__isnull=False).values_list('supervisor_id', flat=True))
            sp_ids = sp_ids + asm_ids + supervisor_ids + [request.user.id]
        else:
            sp_ids = User.objects.filter(role='salesperson', is_active=True).values_list('id', flat=True)
        available_salespeople = User.objects.filter(id__in=list(sp_ids), is_active=True).order_by('first_name','last_name','username')
    return render(request, 'sales_funnel/import_entries.html', {'available_salespeople': available_salespeople})

@login_required
@user_passes_test(is_exec_admin)
def normalize_funnel_stages(request):
    threshold = Decimal('500000')
    qs = SalesFunnel.objects.filter(is_active=True, is_closed=False, stage__in=['project', 'services'])
    to_project = 0
    to_services = 0
    unchanged = 0
    for e in qs.only('id', 'retail', 'stage'):
        desired = 'project' if (e.retail or Decimal('0')) >= threshold else 'services'
        if e.stage != desired:
            e.stage = desired
            e.save(update_fields=['stage', 'updated_at'])
            if desired == 'project':
                to_project += 1
            else:
                to_services += 1
        else:
            unchanged += 1
    messages.success(request, f'Normalized stages: {to_project} → Project, {to_services} → Services, {unchanged} unchanged.')
    return redirect('sales_funnel:dashboard')


@login_required
@user_passes_test(can_import_entries)
def download_sample_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="funnel_import_sample.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'Date Created', 'Company Name', 'Brand', 'Requirement Description', 'Cost', 'SRP', 'Stage',
        'Customer', 'Expected Close Date', 'Probability', 'Notes'
    ])
    writer.writerow([
        '2025-11-01', 'Water District Lipa', 'Dell', 'Laptop i7 16GB RAM 1TB SSD x 10', '450000', '650000', 'Newly Quoted',
        'Water District Lipa', '2025-12-15', '50', 'Include extended warranty'
    ])
    writer.writerow([
        '2025-10-15', 'San Miguel Corporation', 'HP', 'HP Workstation', '500000', '750000', 'Closable This Month',
        'San Miguel Corporation', '2025-11-30', '70', ''
    ])
    writer.writerow([
        '2025-09-20', 'ABC Engineering', 'Cisco', 'Project-based deployment, phased', '300000', '500000', 'Project Based',
        '', '', '40', 'Phase 1 pending approval'
    ])
    writer.writerow([
        '2025-08-05', 'XYZ Medical Center', 'IBM', 'Annual maintenance services package', '120000', '200000', 'Services',
        'XYZ Medical Center', '2025-09-20', '60', 'Includes on-site support'
    ])
    return response


@login_required
@user_passes_test(is_exec_admin)
def clear_stage_entries(request):
    """
    Admin/executive-only bulk cleanup of a stage for a month.

    Safety model:
      * It only ever deletes TEST entries (`is_test=True`) — real pipeline is
        never touched, even here.
      * On PRODUCTION (settings.DEBUG=False) a passcode must be entered that
        matches settings.FUNNEL_CLEAR_STAGE_CODE. On a dev/test machine
        (DEBUG=True) no passcode is required.
    """
    from calendar import monthrange
    from django.conf import settings

    today = timezone.now().date()
    default_month = today.strftime('%Y-%m')
    is_production = not settings.DEBUG
    required_code = (getattr(settings, 'FUNNEL_CLEAR_STAGE_CODE', '') or '').strip()

    def _render(error=None):
        if error:
            messages.error(request, error)
        return render(request, 'sales_funnel/clear_stage.html', {
            'default_month': default_month,
            'is_production': is_production,
            # True only when prod AND an actual code is configured to check against.
            'requires_code': is_production,
        })

    if request.method == 'POST':
        # Production gate: require the configured passcode.
        if is_production:
            if not required_code:
                return _render(
                    'Clear Stage is disabled on production because no '
                    'FUNNEL_CLEAR_STAGE_CODE is configured. Set it in the server .env to enable.'
                )
            submitted = (request.POST.get('clear_code') or '').strip()
            if submitted != required_code:
                return _render('Incorrect passcode. Clear Stage was not run.')

        stage = request.POST.get('stage')
        month_str = request.POST.get('month') or default_month
        try:
            year, month = map(int, month_str.split('-'))
            start_date = datetime(year, month, 1).date()
            end_day = monthrange(year, month)[1]
            end_date = datetime(year, month, end_day).date()
        except Exception:
            return _render('Invalid month format. Use YYYY-MM.')
        if stage not in ['quoted', 'closable', 'project', 'services']:
            return _render('Invalid stage.')

        # Only ever remove TEST, active/open entries — never real pipeline.
        qs = SalesFunnel.objects.filter(
            stage=stage,
            date_created__gte=start_date,
            date_created__lte=end_date,
            is_closed=False,
            is_test=True,
        )
        count = qs.count()
        qs.delete()
        messages.success(
            request,
            f'Cleared {count} TEST entr{"y" if count == 1 else "ies"} from '
            f'"{dict(SalesFunnel.FUNNEL_STAGES).get(stage)}" for {month_str}.'
        )
        return redirect('sales_funnel:dashboard')

    return _render()
