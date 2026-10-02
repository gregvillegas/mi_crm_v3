# -----------------------------------------------------------------------------
# 5. core/views.py (for handling login, logout, and home page)
# -----------------------------------------------------------------------------
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db.models import Sum, Q
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
from sales_funnel.models import SalesFunnel
from teams.models import Team, Group, TeamMembership
from users.models import User
from gamification.models import UserMissionProgress
from gamification.utils import generate_daily_missions, generate_weekly_missions, get_current_week_start
from mass_mailing.models import Campaign, CampaignRecipient, MediaLibraryAsset, Announcement

@login_required
def home(request):
    user = request.user
    context = {'user': user}
    
    # Gamification: Get Daily Missions
    today = timezone.now().date()
    week_start = get_current_week_start(today)

    generate_daily_missions(user)
    generate_weekly_missions(user)

    my_missions = UserMissionProgress.objects.filter(
        user=user
    ).filter(
        Q(mission__mission_type='daily', date_assigned=today) |
        Q(mission__mission_type='weekly', date_assigned=week_start)
    ).select_related('mission').order_by('mission__mission_type', 'mission__title')
    
    context['my_missions'] = my_missions
    
    # Add sales funnel data for eligible users
    if user.role in ['salesperson', 'supervisor', 'teamlead', 'asm', 'avp', 'admin', 'president', 'gm', 'vp']:
        # Get funnel entries based on user role
        if user.role == 'salesperson':
            funnel_entries = SalesFunnel.objects.filter(
                salesperson=user,
                is_active=True,
                is_closed=False
            )
        elif user.role == 'supervisor':
            # Supervisor can see entries from their groups (members + self)
            groups = Group.objects.filter(supervisor=user)
            salespeople_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
            salespeople_ids.append(user.id)
            funnel_entries = SalesFunnel.objects.filter(
                salesperson_id__in=salespeople_ids,
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
            # ASM can see entries from their teams (salespeople + supervisors + self)
            asm_teams = user.asm_teams.all()
            groups = Group.objects.filter(team__in=asm_teams)
            salespeople_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
            supervisor_ids = list(Group.objects.filter(team__in=asm_teams, supervisor__isnull=False).values_list('supervisor_id', flat=True))
            visible_ids = salespeople_ids + supervisor_ids
            funnel_entries = SalesFunnel.objects.filter(
                Q(salesperson_id__in=visible_ids) | Q(salesperson=user),
                is_active=True,
                is_closed=False
            )
        elif user.role == 'sm':
            # SM sees entries from their assigned groups (salespeople + supervisors + self)
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
            # AVP can see entries from their teams (salespeople + supervisors + ASMs + SMs)
            teams = Team.objects.filter(avp=user)
            groups = Group.objects.filter(team__in=teams)
            salespeople_ids = list(TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True))
            asm_ids = list(teams.exclude(asm__isnull=True).values_list('asm_id', flat=True))
            supervisor_ids = list(Group.objects.filter(team__in=teams, supervisor__isnull=False).values_list('supervisor_id', flat=True))
            sm_ids = list(groups.values_list('sm_managers__id', flat=True))
            visible_ids = salespeople_ids + asm_ids + supervisor_ids + [i for i in sm_ids if i]
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
        
        # Calculate funnel statistics
        funnel_stats = {
            'quoted_count': funnel_entries.filter(stage='quoted').count(),
            'closable_count': funnel_entries.filter(stage='closable').count(),
            'project_count': funnel_entries.filter(stage='project').count(),
            'total_value': funnel_entries.aggregate(Sum('retail'))['retail__sum'] or 0,
            'total_entries': funnel_entries.count(),
        }
        
        # Get recent entries for quick view (limit to 5)
        recent_entries = funnel_entries.select_related('salesperson', 'customer').order_by('-date_created')[:5]
        
        context.update({
            'funnel_stats': funnel_stats,
            'recent_funnel_entries': recent_entries,
            'show_funnel': True,
            'can_add_funnel': user.role in ['salesperson', 'supervisor', 'asm', 'avp'],
        })
    
    # ------------------------------------------------------------------
    # Marketing Officer Dashboard
    # ------------------------------------------------------------------
    if user.role == 'marketing':
        campaigns = Campaign.objects.all()
        recipients = CampaignRecipient.objects.all()

        sent_count = recipients.filter(status='sent').count()
        failed_count = recipients.filter(status='failed').count()
        interested_count = recipients.filter(interested_at__isnull=False).count()
        campaigns_sent = campaigns.filter(status='completed').count()

        # Interest rate = interested clicks / successfully sent emails.
        interest_rate = round((interested_count / sent_count) * 100, 1) if sent_count else 0

        # Recent campaigns (annotate each with its interested-click count)
        from django.db.models import Count
        recent_campaigns = campaigns.order_by('-created_at').annotate(
            interested_clicks=Count('recipients', filter=Q(recipients__interested_at__isnull=False))
        )[:5]

        # Recently added media / EDMs in the library
        recent_media = MediaLibraryAsset.objects.order_by('-created_at')[:5]

        # Recent "Interested" clicks to follow up on
        recent_interested = (
            recipients.filter(interested_at__isnull=False)
            .select_related('campaign', 'customer')
            .order_by('-interested_at')[:6]
        )

        # Announcements & upcoming events (active only)
        active_announcements = Announcement.objects.filter(is_active=True)
        upcoming_events = active_announcements.filter(
            announcement_type='event', event_date__gte=timezone.now()
        ).order_by('event_date')[:5]
        recent_announcements = active_announcements.exclude(
            announcement_type='event', event_date__gte=timezone.now()
        ).order_by('-created_at')[:5]

        context.update({
            'show_marketing_dashboard': True,
            'mkt_stats': {
                'campaigns_sent': campaigns_sent,
                'total_campaigns': campaigns.count(),
                'sent_count': sent_count,
                'failed_count': failed_count,
                'interested_count': interested_count,
                'interest_rate': interest_rate,
            },
            'mkt_recent_campaigns': recent_campaigns,
            'mkt_recent_media': recent_media,
            'mkt_recent_interested': recent_interested,
            'mkt_upcoming_events': upcoming_events,
            'mkt_recent_announcements': recent_announcements,
            'mkt_can_manage_announcements': True,
        })

    # ------------------------------------------------------------------
    # Active Users Widget (admin-only)
    # ------------------------------------------------------------------
    if user.role == 'admin':
        threshold_minutes = getattr(settings, 'ONLINE_THRESHOLD_MINUTES', 15)
        cutoff = timezone.now() - timedelta(minutes=threshold_minutes)

        active_users = (
            User.objects
            .filter(last_activity__gte=cutoff, is_active=True)
            .exclude(pk=user.pk)           # exclude self
            .select_related()
            .order_by('-last_activity')
        )

        context.update({
            'active_users': active_users,
            'active_users_count': active_users.count(),
            'online_threshold_minutes': threshold_minutes,
        })

    # Latest from Marketing — company-wide announcements/events for the home card.
    # (Announcement is imported at module top; no local import — that would make
    # the name a function-local and break the marketing branch above.)
    context['latest_announcements'] = list(
        Announcement.objects.filter(is_active=True)
        .select_related('created_by')
        .order_by('-created_at')[:4]
    )

    return render(request, 'core/home.html', context)

@require_POST
def logout_view(request):
    # POST-only: a GET-accessible logout can be triggered by any third-party
    # page (e.g. <img src=".../logout/">), logging users out without consent.
    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('login')


# -----------------------------------------------------------------------------
# Global navbar search
# -----------------------------------------------------------------------------
# Searches four entity types, each scoped to what the current user may see by
# reusing the existing per-app visibility helpers (so the search never leaks a
# record the user couldn't otherwise reach). Users are only searchable by roles
# that can manage users (admin/vp), matching the user-management permission gate.
SEARCH_RESULT_LIMIT = 8
USER_SEARCH_ROLES = {'admin', 'vp'}


@login_required
def global_search(request):
    from customers.permissions import visible_customers_queryset
    from sales_funnel.views import visible_funnel_entries
    from sales_proposals.views import visible_proposals_queryset
    from customers.models import Customer  # noqa: F401 (kept for clarity)

    query = (request.GET.get('q') or '').strip()
    user = request.user

    proposals = customers = funnel_entries = users = []
    counts = {'proposals': 0, 'customers': 0, 'funnel': 0, 'users': 0}

    if query:
        # Proposals — by proposal #, reference #, subject, or customer company.
        proposal_qs = visible_proposals_queryset(user).filter(
            Q(proposal_number__icontains=query)
            | Q(reference_number__icontains=query)
            | Q(subject__icontains=query)
            | Q(customer__company_name__icontains=query)
        ).select_related('customer', 'created_by').order_by('-date')
        counts['proposals'] = proposal_qs.count()
        proposals = list(proposal_qs[:SEARCH_RESULT_LIMIT])

        # Customers — by company, contact person, or email.
        customer_qs = visible_customers_queryset(user).filter(
            Q(company_name__icontains=query)
            | Q(contact_person_name__icontains=query)
            | Q(email__icontains=query)
        ).select_related('salesperson').order_by('company_name')
        counts['customers'] = customer_qs.count()
        customers = list(customer_qs[:SEARCH_RESULT_LIMIT])

        # Funnel entries — by company, brand, or requirement description.
        funnel_qs = visible_funnel_entries(user).filter(
            Q(company_name__icontains=query)
            | Q(brand__icontains=query)
            | Q(requirement_description__icontains=query)
        ).select_related('salesperson', 'customer', 'proposal').order_by('-date_created')
        counts['funnel'] = funnel_qs.count()
        funnel_entries = list(funnel_qs[:SEARCH_RESULT_LIMIT])

        # Users — only for roles permitted to view user management.
        if user.role in USER_SEARCH_ROLES:
            user_qs = User.objects.filter(
                Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
                | Q(initials__icontains=query)
            ).order_by('first_name', 'last_name', 'username')
            counts['users'] = user_qs.count()
            users = list(user_qs[:SEARCH_RESULT_LIMIT])

    context = {
        'query': query,
        'proposals': proposals,
        'customers': customers,
        'funnel_entries': funnel_entries,
        'users': users,
        'counts': counts,
        'result_limit': SEARCH_RESULT_LIMIT,
        'total_results': sum(counts.values()),
        'can_search_users': user.role in USER_SEARCH_ROLES,
    }
    return render(request, 'core/search_results.html', context)
