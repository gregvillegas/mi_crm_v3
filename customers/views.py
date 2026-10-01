from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.db import models, transaction
from django.db.models import Sum
from django.core.paginator import Paginator
from django.utils import timezone
from .models import Customer, CustomerBackup, CustomerHistory, DelinquencyRecord, CustomerNote, CustomerContact, CustomerCreateRequest
from .forms import CustomerForm, CustomerContactFormSet, SalespersonCustomerForm, SalespersonCustomerUpdateForm
from .permissions import (
    can_edit_customer as perms_can_edit_customer,
    can_view_customer as perms_can_view_customer,
    visible_customers_queryset,
    assignment_targets_queryset,
    get_user_team_ids,
    can_review_customer_requests,
    can_approve_customer_requests,
    can_approve_request,
    pending_requests_for_reviewer,
)
from users.models import User
from teams.models import Team, Group, TeamMembership, asm_scoped_groups
from sales_funnel.models import SalesFunnel
from sales_proposals.models import Proposal
from sales_monitoring.models import SalesActivity, ProofOfConcept
from customer_service.models import Ticket
import csv
import io

def is_manager(user):
    return user.role in ['admin', 'avp', 'supervisor', 'asm', 'sm', 'teamlead']

def is_executive(user):
    return user.role in ['admin', 'president', 'gm', 'vp']

def is_admin_or_exec(user):
    return user.role in ['admin', 'gm', 'vp', 'marketing']

@login_required
def add_customer_note(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if not perms_can_view_customer(request.user, customer):
        messages.error(request, 'You do not have permission to add a note to this customer.')
        return redirect('customer_list')
    if request.method == 'POST':
        content = request.POST.get('content')
        if content:
            CustomerNote.objects.create(
                customer=customer,
                author=request.user,
                content=content
            )
            messages.success(request, 'Note added successfully.')
        else:
            messages.error(request, 'Note content cannot be empty.')
    return redirect('customer_detail', pk=pk)

@login_required
def customer_list(request):
    user = request.user
    customers = visible_customers_queryset(user)
    view_mode = request.GET.get('view', 'table')

    # Apply filters based on GET parameters
    status_filter = request.GET.get('status')
    millionaire_filter = request.GET.get('millionaire') or request.GET.get('vip')
    industry_filter = request.GET.get('industry')
    territory_filter = request.GET.get('territory')
    search_query = request.GET.get('search')
    salesperson_filter = request.GET.get('salesperson')
    team_filter = request.GET.get('team')
    group_filter = request.GET.get('group')
    
    if status_filter == 'active':
        customers = customers.filter(is_active=True, auto_inactive_flag=False)
    elif status_filter == 'inactive':
        customers = customers.filter(models.Q(is_active=False) | models.Q(auto_inactive_flag=True))
    
    if millionaire_filter == 'yes':
        customers = customers.filter(is_millionaire_account=True)
    elif millionaire_filter == 'no':
        customers = customers.filter(is_millionaire_account=False)
    
    if industry_filter and industry_filter != '':
        customers = customers.filter(industry=industry_filter)
    
    if territory_filter and territory_filter != '':
        customers = customers.filter(territory=territory_filter)
    
    if search_query:
        customers = customers.filter(
            models.Q(company_name__icontains=search_query) |
            models.Q(contact_person_name__icontains=search_query) |
            models.Q(email__icontains=search_query)
        )
    
    # Salesperson filter
    if salesperson_filter:
        if salesperson_filter == 'unassigned':
            customers = customers.filter(salesperson__isnull=True)
        else:
            try:
                sp_id = int(salesperson_filter)
                customers = customers.filter(salesperson_id=sp_id)
            except ValueError:
                pass

    # Team / Group filters (granular search for executive roles + AVP).
    # Path: Customer.salesperson -> TeamMembership.group -> Group.team
    #
    # Execs + AVP get BOTH a Team and a Group dropdown. ASM/SM get ONLY a Group
    # dropdown, limited to the groups THEY handle (option A) — mirroring the
    # Sales Proposals dashboard. The selected group is validated against that
    # allowed set so a hand-typed ?group= can't widen the (already-scoped) view.
    show_team_group_filters = user.role in ['admin', 'gm', 'vp', 'president', 'avp']
    show_group_filter = user.role in ['asm', 'sm']
    if show_team_group_filters:
        if team_filter:
            try:
                customers = customers.filter(
                    salesperson__team_membership__group__team_id=int(team_filter)
                )
            except (ValueError, TypeError):
                pass
        if group_filter:
            try:
                customers = customers.filter(
                    salesperson__team_membership__group_id=int(group_filter)
                )
            except (ValueError, TypeError):
                pass
    elif show_group_filter:
        if user.role == 'asm':
            allowed_groups = asm_scoped_groups(user)
        else:  # sm
            allowed_groups = user.sm_groups.all()
        allowed_group_ids = set(allowed_groups.values_list('id', flat=True))
        if group_filter:
            try:
                if int(group_filter) in allowed_group_ids:
                    customers = customers.filter(
                        salesperson__team_membership__group_id=int(group_filter)
                    )
                else:
                    group_filter = ''
            except (ValueError, TypeError):
                group_filter = ''
    
    # Duplicates filter — show only customers with similar/duplicate company names
    duplicates_filter = request.GET.get('duplicates', '')
    duplicate_groups = []
    if duplicates_filter == 'yes' and user.role in ['admin', 'gm', 'vp', 'marketing', 'avp', 'asm', 'sm', 'supervisor']:
        from collections import defaultdict
        # Build a map of normalized name → list of customer IDs
        norm_map = defaultdict(list)
        for c in customers.only('id', 'company_name'):
            norm = _normalize_company_name(c.company_name)
            if norm:
                norm_map[norm].append(c.id)
        # Keep only groups with 2+ customers (exact-match after normalization)
        dup_ids = set()
        for norm_name, ids in norm_map.items():
            if len(ids) >= 2:
                dup_ids.update(ids)
                duplicate_groups.append({
                    'normalized_name': norm_name,
                    'ids': ids,
                })
        if dup_ids:
            customers = customers.filter(id__in=dup_ids)
        else:
            customers = customers.none()

    # Order by millionaire status first, then by creation date
    if duplicates_filter == 'yes':
        customers = customers.select_related('salesperson').order_by('company_name')
    else:
        customers = customers.select_related('salesperson').order_by('-is_millionaire_account', '-created_at')
    
    # Available salespeople for filter dropdown (active only)
    available_salespeople = assignment_targets_queryset(user)

    # Team / Group options for granular filtering.
    # Executives see all teams/groups; AVP is scoped to their managed teams only.
    available_teams = []
    available_groups = []
    if show_team_group_filters:
        if user.role == 'avp':
            avp_team_ids = get_user_team_ids(user)
            available_teams = Team.objects.filter(id__in=avp_team_ids).order_by('name')
            available_groups = (
                Group.objects.select_related('team')
                .filter(team_id__in=avp_team_ids)
                .order_by('team__name', 'name')
            )
        else:
            available_teams = Team.objects.all().order_by('name')
            available_groups = Group.objects.select_related('team').all().order_by('team__name', 'name')
    elif show_group_filter:
        # ASM/SM: Group dropdown limited to the groups they handle.
        if user.role == 'asm':
            scoped_groups = asm_scoped_groups(user)
        else:  # sm
            scoped_groups = user.sm_groups.all()
        available_groups = (
            Group.objects.select_related('team')
            .filter(id__in=scoped_groups.values_list('id', flat=True))
            .order_by('team__name', 'name')
        )
    
    # Determine if user can see admin actions column
    # Admin, VP, GM, Marketing: Full access
    # AVP, ASM, Supervisor: Transfer access
    can_manage_customers = user.role in ['admin', 'gm', 'vp', 'marketing', 'avp', 'asm', 'sm', 'supervisor']

    # Pending create-requests the user is allowed to review.
    # admin/gm/vp/marketing => all; avp => only their own team's requests.
    pending_create_count = pending_requests_for_reviewer(user).count()

    # Stats are computed over the FULL filtered queryset (before pagination) so
    # the summary cards always reflect every matching customer, not just the
    # page currently on screen.
    stats = {
        'total': customers.count(),
        'millionaire_count': customers.filter(is_millionaire_account=True).count(),
        'active_count': customers.filter(is_active=True, auto_inactive_flag=False).count(),
        'inactive_count': customers.filter(models.Q(is_active=False) | models.Q(auto_inactive_flag=True)).count(),
    }

    # Paginate the customer list. Long lists are hard to scroll, so we page the
    # results. Page size can be overridden via ?per_page= (capped for safety).
    try:
        per_page = int(request.GET.get('per_page', 25))
    except (TypeError, ValueError):
        per_page = 25
    per_page = max(10, min(per_page, 200))

    paginator = Paginator(customers, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))

    # Preserve all active filters (everything except 'page') so pagination
    # links keep the current search/filter/view state.
    querystring = request.GET.copy()
    querystring.pop('page', None)
    preserved_query = querystring.urlencode()

    # Get filter options for the template
    context = {
        'customers': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'is_paginated': page_obj.has_other_pages(),
        'per_page': per_page,
        'preserved_query': preserved_query,
        'view_mode': view_mode,
        'show_actions': can_manage_customers,
        'industry_choices': Customer.INDUSTRY_CHOICES,
        'territory_choices': Customer.TERRITORY_CHOICES,
        'available_salespeople': available_salespeople,
        'available_teams': available_teams,
        'available_groups': available_groups,
        'show_team_group_filters': show_team_group_filters,
        'show_group_filter': show_group_filter,
        'current_filters': {
            'status': status_filter,
            'millionaire': millionaire_filter,
            'industry': industry_filter,
            'territory': territory_filter,
            'search': search_query or '',
            'salesperson': salesperson_filter or '',
            'team': team_filter or '',
            'group': group_filter or '',
            'duplicates': duplicates_filter or '',
            'view': view_mode,
            'per_page': per_page,
        },
        'stats': stats,
        'pending_create_count': pending_create_count,
        'duplicate_group_count': len(duplicate_groups),
    }
    
    return render(request, 'customers/customer_list.html', context)

@login_required
def customer_contacts(request, pk):
    """Return up to 4 contacts for a customer in JSON for dependent dropdowns."""
    customer = get_object_or_404(Customer, pk=pk)
    if not perms_can_view_customer(request.user, customer):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    # Convert queryset to list of dicts
    additional = list(CustomerContact.objects.filter(customer=customer).order_by('-is_primary','name').values('id','name','position','email','phone','is_primary'))
    # Always include legacy main contact as an option
    main_contact = {
        'id': 'main',
        'name': customer.contact_person_name or '',
        'position': customer.contact_person_position or '',
        'email': customer.email or '',
        'phone': customer.phone_number or '',
        'is_primary': False
    }
    # If no additional primary is set, make main contact primary by default
    if not any(c.get('is_primary') for c in additional):
        main_contact['is_primary'] = True
    # Build final list with main first, then additional (de-duplicate by name+email)
    seen = set()
    contacts = []
    for c in [main_contact] + additional:
        key = (c.get('name','').strip().lower(), (c.get('email') or '').strip().lower())
        if key in seen:
            continue
        seen.add(key)
        contacts.append(c)
    return JsonResponse({'contacts': contacts})

@login_required
def delinquent_list(request):
    user = request.user
    records = DelinquencyRecord.objects.filter(status__in=['open','watch']).select_related('customer','salesperson')
    # Filters (simplified to match current UI/fields)
    search = request.GET.get('search')
    tin = request.GET.get('tin')
    partner = request.GET.get('partner')
    ae = request.GET.get('ae')
    if search:
        records = records.filter(
            models.Q(customer__company_name__icontains=search) |
            models.Q(remarks__icontains=search)
        )
    if tin:
        records = records.filter(tin_number__icontains=tin)
    if partner:
        records = records.filter(partner_name__icontains=partner)
    if ae:
        try:
            ae_id = int(ae)
            records = records.filter(models.Q(salesperson_id=ae_id))
        except Exception:
            pass
    # Available AE list for dropdown (all)
    from users.models import User
    available_ae = User.objects.filter(is_active=True, role__in=['salesperson','supervisor','asm','sm','avp'])
    context = {
        'records': records.order_by('customer__company_name'),
        'current_filters': {
            'search': search or '',
            'tin': tin or '',
            'partner': partner or '',
            'ae': int(ae) if (ae and ae.isdigit()) else '',
        },
        'available_ae': available_ae.order_by('first_name','last_name','username')
    }
    return render(request, 'customers/delinquent_list.html', context)

import re
from difflib import SequenceMatcher

def _normalize_company_name(name: str) -> str:
    if not name:
        return ''
    s = name.lower()
    s = re.sub(r'[^a-z0-9\s]', ' ', s)  # remove punctuation
    tokens = [t for t in s.split() if t]
    suffixes = {'corp', 'corporation', 'inc', 'incorporated', 'co', 'company', 'ltd', 'limited', 'llc', 'gmbh', 'sa', 'plc'}
    # remove common suffixes from the end
    while tokens and tokens[-1] in suffixes:
        tokens.pop()
    return ' '.join(tokens)

def _find_similar_customers(company_name, threshold=0.75):
    base = _normalize_company_name(company_name)
    matches = []
    if not base:
        return matches
    for c in Customer.objects.select_related('salesperson').all():
        norm = _normalize_company_name(c.company_name)
        if not norm:
            continue
        # Jaccard on tokens
        a, b = set(base.split()), set(norm.split())
        jacc = (len(a & b) / len(a | b)) if (a | b) else 0
        ratio = SequenceMatcher(None, base, norm).ratio()
        subset_bonus = 0.1 if (a.issubset(b) or b.issubset(a)) else 0
        score = min(1.0, max(jacc, ratio) + subset_bonus)
        if score >= threshold:
            matches.append(_serialize_similar_match(c, round(score, 3)))
    return sorted(matches, key=lambda m: m['score'], reverse=True)[:5]


def _serialize_similar_match(customer, score):
    salesperson = customer.salesperson
    return {
        'id': customer.id,
        'company_name': customer.company_name,
        'score': round(score, 3),
        'salesperson_initials': (salesperson.initials or salesperson.username[:3].upper()) if salesperson else '',
        'salesperson_name': ((salesperson.get_full_name() or salesperson.username) if salesperson else 'Unassigned'),
        'status': customer.display_status or 'Unknown',
    }


def _enrich_similar_matches(matches):
    if not matches:
        return []
    match_ids = [m.get('id') for m in matches if m.get('id')]
    customers_by_id = {
        customer.id: customer
        for customer in Customer.objects.select_related('salesperson').filter(id__in=match_ids)
    }
    enriched = []
    for match in matches:
        customer = customers_by_id.get(match.get('id'))
        if customer:
            current = _serialize_similar_match(customer, match.get('score', 0))
            current['score'] = match.get('score', current['score'])
            enriched.append(current)
        else:
            enriched.append({
                'id': match.get('id'),
                'company_name': match.get('company_name', 'Unknown Customer'),
                'score': match.get('score', 0),
                'salesperson_initials': match.get('salesperson_initials', ''),
                'salesperson_name': match.get('salesperson_name', 'Unassigned'),
                'status': match.get('status') or 'Unknown',
            })
    return enriched

@login_required
def create_customer(request):
    user = request.user
    
    # Salespeople can request creation (with duplicate check/approval); managers can create directly
    is_salesperson = user.role == 'salesperson'
    if not is_salesperson and user.role not in ['admin', 'gm', 'vp', 'marketing', 'avp', 'supervisor', 'asm', 'sm', 'teamlead']:
        messages.error(request, "You don't have permission to create customers.")
        return redirect('customer_list')
    
    if request.method == 'POST':
        if is_salesperson:
            form = SalespersonCustomerForm(request.POST, salesperson=user)
            if form.is_valid():
                company_name = form.cleaned_data.get('company_name','')
                similar = _find_similar_customers(company_name)
                if similar:
                    # Open approval request instead of direct creation
                    req = CustomerCreateRequest.objects.create(
                        company_name=form.cleaned_data['company_name'],
                        contact_person_name=form.cleaned_data['contact_person_name'],
                        contact_person_position=form.cleaned_data.get('contact_person_position',''),
                        email=form.cleaned_data['email'],
                        phone_number=form.cleaned_data.get('phone_number',''),
                        address=form.cleaned_data.get('address',''),
                        industry=form.cleaned_data.get('industry',''),
                        territory=form.cleaned_data.get('territory',''),
                        requested_by=user,
                        similar_matches=similar
                    )
                    messages.warning(request, "A similar customer exists. Your request has been sent to AVP for approval.")
                    return redirect('customer_list')
                # No similar found: proceed to create and assign
                customer = form.save()
                messages.success(request, f'Customer "{customer.company_name}" has been created successfully!')
                return redirect('customer_list')
            # invalid form
            context = {'form': form, 'contact_formset': None, 'title': 'Add New Customer', 'is_salesperson_form': True}
            return render(request, 'customers/customer_form.html', context)
        else:
            form = CustomerForm(request.POST, user=user)
            if form.is_valid():
                customer = form.save()
                contact_formset = CustomerContactFormSet(request.POST, instance=customer)
                if contact_formset.is_valid():
                    contact_formset.save()
                    messages.success(request, f'Customer "{customer.company_name}" has been created successfully!')
                    return redirect('customer_list')
                else:
                    context = {
                        'form': form,
                        'contact_formset': contact_formset,
                        'title': 'Create New Customer',
                        'is_salesperson_form': False
                    }
                    return render(request, 'customers/customer_form.html', context)
            else:
                contact_formset = CustomerContactFormSet(request.POST)
                context = {
                    'form': form,
                    'contact_formset': contact_formset,
                    'title': 'Create New Customer',
                    'is_salesperson_form': False
                }
                return render(request, 'customers/customer_form.html', context)
    else:
        if is_salesperson:
            form = SalespersonCustomerForm(salesperson=user)
            context = {'form': form, 'contact_formset': None, 'title': 'Add New Customer', 'is_salesperson_form': True}
        else:
            form = CustomerForm(user=user)
            contact_formset = CustomerContactFormSet()
            context = {
                'form': form,
                'contact_formset': contact_formset,
                'title': 'Create New Customer',
                'is_salesperson_form': False
            }
    
    return render(request, 'customers/customer_form.html', context)

@login_required
def customer_create_requests(request):
    if not can_review_customer_requests(request.user):
        messages.error(request, "You don't have access to approval requests.")
        return redirect('customer_list')
    # Scoped to what this reviewer may see: execs => all; AVP/managers => own scope.
    qs = pending_requests_for_reviewer(request.user).select_related('requested_by')
    for req in qs:
        req.display_similar_matches = _enrich_similar_matches(req.similar_matches)
    # Watchers (supervisor/sm/asm) see the list read-only; only approvers act.
    can_approve = can_approve_customer_requests(request.user)
    return render(request, 'customers/customer_create_requests.html', {
        'requests': qs,
        'can_approve': can_approve,
    })

@login_required
def approve_customer_request(request, pk):
    if not can_approve_customer_requests(request.user):
        messages.error(request, "You don't have permission to approve customer requests.")
        return redirect('customer_list')
    req = get_object_or_404(CustomerCreateRequest, pk=pk)
    # AVPs may only act on requests from their own team.
    if not can_approve_request(request.user, req):
        messages.error(request, "This request is outside your team and can only be reviewed by its AVP or an executive.")
        return redirect('customer_create_requests')
    if request.method == 'POST':
        if req.status != 'pending':
            messages.warning(request, f'This request has already been {req.get_status_display().lower()} by {req.reviewed_by.get_full_name() if req.reviewed_by else "another user"}.')
            return redirect('customer_create_requests')
        customer = req.approve(request.user)
        if customer:
            messages.success(request, f'Request approved. Customer "{customer.company_name}" created.')
        else:
            messages.warning(request, 'This request was already processed by another user.')
    return redirect('customer_create_requests')

@login_required
def reject_customer_request(request, pk):
    if not can_approve_customer_requests(request.user):
        messages.error(request, "You don't have permission to reject customer requests.")
        return redirect('customer_list')
    req = get_object_or_404(CustomerCreateRequest, pk=pk)
    # AVPs may only act on requests from their own team.
    if not can_approve_request(request.user, req):
        messages.error(request, "This request is outside your team and can only be reviewed by its AVP or an executive.")
        return redirect('customer_create_requests')
    if request.method == 'POST':
        note = request.POST.get('note','')
        req.reject(request.user, notes=note)
        messages.warning(request, 'Request rejected.')
    return redirect('customer_create_requests')

@login_required
def customer_create_request_history(request):
    if request.user.role not in ['admin', 'avp', 'gm', 'vp', 'marketing', 'salesperson']:
        messages.error(request, "You don't have access to request history.")
        return redirect('customer_list')
    # In the history view, marketing sees all requests (not just their own)
    if request.user.role == 'salesperson':
        qs = CustomerCreateRequest.objects.filter(requested_by=request.user).exclude(status='pending').order_by('-reviewed_at', '-created_at')
        unseen_ids = list(qs.filter(requester_seen_at__isnull=True).values_list('id', flat=True))
        if unseen_ids:
            CustomerCreateRequest.objects.filter(id__in=unseen_ids).update(requester_seen_at=timezone.now())
        page_title = 'My Customer Request History'
    else:
        qs = CustomerCreateRequest.objects.exclude(status='pending').order_by('-reviewed_at', '-created_at')
        page_title = 'Customer Request History'
    return render(request, 'customers/customer_create_requests_history.html', {'requests': qs, 'page_title': page_title})

@login_required
def transfer_customer(request, pk):
    # Permission check: Admin, VP, GM, Marketing, AVP, Supervisor, ASM
    if request.user.role not in ['admin', 'vp', 'gm', 'marketing', 'avp', 'supervisor', 'asm', 'sm']:
        messages.error(request, "You don't have permission to transfer customers.")
        return redirect('customer_list')

    customer = get_object_or_404(Customer, pk=pk)
    if not perms_can_edit_customer(request.user, customer):
        messages.error(request, "You don't have permission to transfer this customer.")
        return redirect('customer_list')
    if request.method == 'POST':
        new_salesperson_id = request.POST.get('salesperson')
        targets = assignment_targets_queryset(request.user)
        new_salesperson = get_object_or_404(targets, id=new_salesperson_id)
        customer.salesperson = new_salesperson
        customer.save()
        messages.success(request, f'Customer "{customer.company_name}" has been transferred to {new_salesperson.get_full_name()}.')
        return redirect('customer_list')

    # Get available salespeople based on role (could be filtered by team in future)
    salespeople = assignment_targets_queryset(request.user)
    return render(request, 'customers/transfer_customer.html', {'customer': customer, 'salespeople': salespeople})


def is_admin(user):
    return user.role in ['admin', 'marketing']


def decode_csv_bytes(raw):
    """
    Decode uploaded CSV bytes to text safely, preserving special characters
    such as the Spanish ñ (e.g. "Parañaque").

    Strategy (best practice — no silent corruption):
      1. Try UTF-8 (with/without BOM) strictly. This is the recommended format
         and the only one that unambiguously represents ñ/é/etc.
      2. If that fails, use charset-normalizer to DETECT the real encoding and
         decode with it (handles legacy Excel exports like cp1252).
      3. As an explicit last resort, decode as cp1252 (Windows Excel default).
         latin-1 is NOT used as a catch-all because it never errors and would
         silently produce garbled characters.

    Returns the decoded string, or None if the file cannot be decoded
    confidently — callers should then ask the user to re-save as UTF-8.
    """
    if raw is None:
        return None

    # 1) Strict UTF-8 first (utf-8-sig transparently strips the Excel BOM).
    #    This is the ONLY encoding that represents ñ unambiguously — always prefer it.
    for encoding in ('utf-8-sig', 'utf-8'):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, ValueError):
            continue

    # Not UTF-8. There is no fully reliable way to detect a legacy single-byte
    # encoding (e.g. the byte 0xF1 is 'ñ' in cp1252/latin-1 but 'ń' in cp1250),
    # so we prefer cp1252 — the default Windows/Excel export in this region, where
    # 0xF1 correctly maps to 'ñ'. Detection is only used if cp1252 itself fails.

    # 2) cp1252 (Windows Excel default). Decodes the full 0x80–0xFF range,
    #    so it won't raise on typical Excel CSVs and yields the correct ñ.
    try:
        return raw.decode('cp1252')
    except (UnicodeDecodeError, ValueError):
        pass

    # 3) Fallback: let charset-normalizer detect anything more exotic
    #    (e.g. UTF-16, Shift-JIS). Best-effort only.
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(raw).best()
        if best is not None:
            return str(best)
    except Exception:
        pass

    # 4) Give up — caller will ask the user to re-save as UTF-8.
    return None


def _decode_csv_upload(csv_file):
    """Read an uploaded file object and decode it. Returns text or None."""
    return decode_csv_bytes(csv_file.read())


def _normalize_csv_row(row):
    normalized = {}
    for key, value in row.items():
        normalized_key = (key or '').strip().lower().replace(' ', '_')
        normalized[normalized_key] = value
    return normalized


def _first_csv_value(row, keys):
    normalized = _normalize_csv_row(row)
    for key in keys:
        value = normalized.get(key)
        if value is not None:
            return str(value).strip()
    return ''


def _parse_csv_bool(value):
    return str(value).strip().lower() in ['yes', 'true', '1', 'y']


def _map_customer_choice(raw_value, choices):
    value = (raw_value or '').strip()
    if not value:
        return ''

    import unicodedata

    def _normalize_choice_text(text):
        normalized = str(text).strip().lower()
        # Normalize unicode (handles combining characters, different ñ representations)
        normalized = unicodedata.normalize('NFC', normalized)
        if normalized.endswith(' city'):
            normalized = normalized[:-5]
        normalized = normalized.replace('&', 'and')
        normalized = normalized.replace('<', ' ').replace('>', ' ')
        normalized = normalized.replace('(', ' ').replace(')', ' ')
        normalized = ' '.join(normalized.replace('/', ' ').split())
        return normalized

    lowered = _normalize_choice_text(value)
    display_to_value = {
        _normalize_choice_text(label): db_value
        for db_value, label in choices
    }
    value_to_value = {
        _normalize_choice_text(db_value): db_value
        for db_value, _label in choices
    }

    if lowered in value_to_value:
        return value_to_value[lowered]
    if lowered in display_to_value:
        return display_to_value[lowered]

    for db_value, label in choices:
        normalized_label = _normalize_choice_text(label)
        normalized_db_value = _normalize_choice_text(db_value)
        if lowered in normalized_label or lowered in normalized_db_value:
            return db_value
    return None


def _customer_with_contacts_header():
    header = [
        'company_name',
        'contact_person_name',
        'contact_person_position',
        'email',
        'phone_number',
        'address',
        'industry',
        'territory',
        'active_status',
        'salesperson_initials',
    ]
    for index in range(2, 6):
        header.extend([
            f'contact_{index}_name',
            f'contact_{index}_position',
            f'contact_{index}_email',
            f'contact_{index}_phone',
            f'contact_{index}_is_primary',
        ])
    return header


@login_required
@user_passes_test(is_admin)
def export_customers(request):
    """Export all customers to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="customers_export.csv"'
    
    writer = csv.writer(response)
    # Write header
    writer.writerow([
        'Company Name', 'Contact Person Name', 'Contact Person Position', 'Email', 'Phone Number', 'Address', 
        'Industry', 'Territory', 'Millionaire Status', 'Active Status', 'Salesperson Initials',
        'Created At', 'Updated At'
    ])
    
    # Write customer data
    customers = Customer.objects.all().select_related('salesperson')
    for customer in customers:
        salesperson_initials = customer.salesperson.initials if customer.salesperson and customer.salesperson.initials else ''
        writer.writerow([
            customer.company_name,
            customer.contact_person_name,
            customer.contact_person_position,
            customer.email,
            customer.phone_number,
            customer.address,
            customer.get_industry_display() if customer.industry else '',
            customer.get_territory_display() if customer.territory else '',
            'Yes' if customer.is_millionaire_account else 'No',
            'Yes' if customer.is_effectively_active else 'No',
            salesperson_initials,
            customer.created_at.strftime('%Y-%m-%d %H:%M:%S') if customer.created_at else '',
            customer.updated_at.strftime('%Y-%m-%d %H:%M:%S') if customer.updated_at else '',
        ])
    
    return response


@login_required
@user_passes_test(is_admin)
def export_customers_with_contacts(request):
    """Export customers in the one-row-per-customer format used by the customer+contacts importer."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="customers_with_contacts_export.csv"'

    writer = csv.writer(response)
    writer.writerow(_customer_with_contacts_header())

    customers = (
        Customer.objects.all()
        .select_related('salesperson')
        .prefetch_related('contacts')
        .order_by('company_name', 'id')
    )

    for customer in customers:
        salesperson_initials = customer.salesperson.initials if customer.salesperson and customer.salesperson.initials else ''
        row = [
            customer.company_name,
            customer.contact_person_name,
            customer.contact_person_position,
            customer.email,
            customer.phone_number,
            customer.address,
            customer.get_industry_display() if customer.industry else '',
            customer.get_territory_display() if customer.territory else '',
            'Yes' if customer.is_active else 'No',
            salesperson_initials,
        ]

        contacts = list(customer.contacts.all()[:4])
        for contact in contacts:
            row.extend([
                contact.name,
                contact.position,
                contact.email or '',
                contact.phone,
                'Yes' if contact.is_primary else 'No',
            ])

        remaining_slots = 4 - len(contacts)
        for _ in range(remaining_slots):
            row.extend(['', '', '', '', ''])

        writer.writerow(row)

    return response

@login_required
@user_passes_test(is_admin)
def import_customers(request):
    """Import customers from CSV"""
    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            messages.error(request, 'Please select a CSV file to upload.')
            return redirect('customer_list')
        
        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'Please upload a valid CSV file.')
            return redirect('customer_list')
        
        try:
            # Decode safely (preserves ñ; no silent corruption).
            decoded_file = decode_csv_bytes(csv_file.read())

            if decoded_file is None:
                messages.error(
                    request,
                    'Unable to read the CSV file. Please re-save it as "CSV UTF-8" '
                    '(in Excel: Save As → CSV UTF-8) and upload again.'
                )
                return redirect('customer_list')

            csv_data = csv.reader(io.StringIO(decoded_file))
            
            # Skip header row
            header_row = next(csv_data, None)
            if not header_row:
                messages.error(request, 'The CSV file is missing a header row.')
                return redirect('customer_list')

            detected_headers = [
                str(header).strip()
                for header in header_row
                if str(header).strip()
            ]
            normalized_headers = [
                str(header).strip().lower().replace(' ', '_')
                for header in header_row
                if str(header).strip()
            ]
            normalized_header_set = set(normalized_headers)

            looks_like_contacts_only_import = (
                {'customer_email', 'contact_name'}.issubset(normalized_header_set)
                and 'company_name' not in normalized_header_set
                and 'contact_person_name' not in normalized_header_set
            )

            if looks_like_contacts_only_import:
                messages.error(
                    request,
                    'This file looks like a contacts-only CSV, not a customer import CSV. '
                    'Use Import Contacts instead. '
                    f'Detected headers: {", ".join(detected_headers) or "none"}. '
                    f'Normalized headers: {", ".join(normalized_headers) or "none"}.'
                )
                return redirect('customer_list')
            
            created_count = 0
            updated_count = 0
            skipped_duplicates_in_file = 0
            errors = []
            seen_emails = set()
            
            for row_num, row in enumerate(csv_data, start=2):
                if len(row) < 5:  # Minimum required fields
                    errors.append(f'Row {row_num}: Not enough columns')
                    continue
                
                # Extract all columns based on export format
                company_name = (row[0] if len(row) > 0 else '').strip()
                contact_person_name = (row[1] if len(row) > 1 else '').strip()
                contact_person_position = (row[2] if len(row) > 2 else '').strip()
                email_raw = (row[3] if len(row) > 3 else '').strip()
                phone_number = (row[4] if len(row) > 4 else '').strip()
                address = (row[5] if len(row) > 5 else '').strip()
                industry = (row[6] if len(row) > 6 else '').strip()
                territory = (row[7] if len(row) > 7 else '').strip()
                active_status_raw = (row[9] if len(row) > 9 else '').strip()
                salesperson_initials = (row[10] if len(row) > 10 else '').strip()
                # Skip Created At and Updated At (columns 11-12) as they're auto-generated

                if not any([company_name, contact_person_name, email_raw, phone_number, address, industry, territory, salesperson_initials, active_status_raw]):
                    continue

                email = email_raw.lower()
                if not email:
                    errors.append(f'Row {row_num}: Email is required')
                    continue

                company_name_key = company_name.strip().lower()
                dedupe_key = (company_name_key, email)

                if dedupe_key in seen_emails:
                    skipped_duplicates_in_file += 1
                    continue

                seen_emails.add(dedupe_key)

                existing_candidates = Customer.objects.filter(email__iexact=email)
                existing_customer = None
                if company_name:
                    existing_customer = existing_candidates.filter(company_name__iexact=company_name).first()

                if not existing_customer and (not company_name or not contact_person_name):
                    errors.append(f'Row {row_num}: Company name and contact person name are required for new customers')
                    continue
                
                # Validate and convert industry
                industry_value = _map_customer_choice(industry, Customer.INDUSTRY_CHOICES)
                if industry and industry_value is None:
                    errors.append(f'Row {row_num}: Invalid industry "{industry}"')
                    continue
                
                # Validate and convert territory
                territory_value = _map_customer_choice(territory, Customer.TERRITORY_CHOICES)
                if territory and territory_value is None:
                    errors.append(f'Row {row_num}: Invalid territory "{territory}"')
                    continue
                
                is_active = active_status_raw.lower() in ['yes', 'true', '1'] if active_status_raw else None
                
                # Get salesperson if initials are provided
                salesperson = None
                if salesperson_initials:
                    try:
                        salesperson = User.objects.get(initials=salesperson_initials, role__in=['salesperson', 'supervisor', 'asm', 'sm', 'avp'], is_active=True)
                    except User.DoesNotExist:
                        errors.append(f'Row {row_num}: Active salesperson with initials "{salesperson_initials}" not found')
                        continue
                
                # Create or update customer
                try:
                    if existing_customer:
                        if company_name:
                            existing_customer.company_name = company_name
                        if contact_person_name:
                            existing_customer.contact_person_name = contact_person_name
                        if contact_person_position:
                            existing_customer.contact_person_position = contact_person_position
                        if phone_number:
                            existing_customer.phone_number = phone_number
                        if address:
                            existing_customer.address = address
                        if industry or industry_value is not None:
                            existing_customer.industry = industry_value or ''
                        if territory or territory_value is not None:
                            existing_customer.territory = territory_value or ''
                        if is_active is not None:
                            existing_customer.is_active = is_active
                        if salesperson is not None:
                            existing_customer.salesperson = salesperson
                        existing_customer.save()
                        updated_count += 1
                    else:
                        Customer.objects.create(
                            company_name=company_name,
                            contact_person_name=contact_person_name,
                            contact_person_position=contact_person_position,
                            email=email,
                            phone_number=phone_number,
                            address=address,
                            industry=industry_value or '',
                            territory=territory_value or '',
                            is_active=is_active if is_active is not None else True,
                            salesperson=salesperson
                        )
                        created_count += 1
                except Exception as e:
                    errors.append(f'Row {row_num}: Error saving customer - {str(e)}')
            
            if created_count or updated_count:
                messages.success(
                    request,
                    f'Successfully processed customers. Created: {created_count}. Updated: {updated_count}.'
                    + (f' Skipped duplicates in file: {skipped_duplicates_in_file}.' if skipped_duplicates_in_file else '')
                )
            
            if errors:
                error_message = f'Encountered {len(errors)} errors:\n' + '\n'.join(errors[:10])
                if len(errors) > 10:
                    error_message += f'\n... and {len(errors) - 10} more errors.'
                messages.warning(request, error_message)
                
        except Exception as e:
            messages.error(request, f'Error processing CSV file: {str(e)}')
        
        return redirect('customer_list')
    
    return render(request, 'customers/import_customers.html')


@login_required
@user_passes_test(is_admin)
def import_customer_contacts(request):
    """Import additional customer contacts from CSV without changing Customer records."""
    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            messages.error(request, 'Please select a CSV file to upload.')
            return redirect('import_customer_contacts')

        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'Please upload a valid CSV file.')
            return redirect('import_customer_contacts')

        try:
            decoded_text = decode_csv_bytes(csv_file.read())

            if decoded_text is None:
                messages.error(
                    request,
                    'Unable to read the CSV file. Please re-save it as "CSV UTF-8" and upload again.'
                )
                return redirect('import_customer_contacts')

            reader = csv.DictReader(io.StringIO(decoded_text))
            if not reader.fieldnames:
                messages.error(request, 'The CSV file is missing a header row.')
                return redirect('import_customer_contacts')

            detected_headers = [
                (header or '').strip()
                for header in reader.fieldnames
                if (header or '').strip()
            ]
            normalized_headers = [
                header.strip().lower().replace(' ', '_')
                for header in reader.fieldnames
                if (header or '').strip()
            ]
            normalized_header_set = set(normalized_headers)

            looks_like_customer_import = (
                'customer_email' not in normalized_header_set
                and 'contact_name' not in normalized_header_set
                and {
                    'company_name',
                    'contact_person_name',
                    'email',
                }.issubset(normalized_header_set)
            )

            if looks_like_customer_import:
                has_extra_contact_columns = any(
                    header.startswith('contact_2_') for header in normalized_headers
                )
                suggested_import = (
                    'Import Customers + Contacts'
                    if has_extra_contact_columns
                    else 'Legacy Customer Import'
                )
                messages.error(
                    request,
                    'This file looks like a customer import CSV, not a contacts-only CSV. '
                    f'Use {suggested_import} instead. '
                    f'Detected headers: {", ".join(detected_headers) or "none"}. '
                    f'Normalized headers: {", ".join(normalized_headers) or "none"}.'
                )
                return redirect('import_customer_contacts')

            def _first_value(row, keys):
                normalized = {}
                for key, value in row.items():
                    normalized_key = (key or '').strip().lower().replace(' ', '_')
                    normalized[normalized_key] = value
                for key in keys:
                    value = normalized.get(key)
                    if value is not None:
                        return str(value).strip()
                return ''

            def _parse_bool(value):
                return str(value).strip().lower() in ['yes', 'true', '1', 'y']

            created_count = 0
            updated_count = 0
            errors = []

            for row_num, row in enumerate(reader, start=2):
                customer_email = _first_value(row, ['customer_email', 'customer'])
                company_name = _first_value(row, ['company_name', 'customer_company', 'company'])
                contact_name = _first_value(row, ['contact_name', 'name'])
                position = _first_value(row, ['contact_position', 'position', 'title'])
                contact_email = _first_value(row, ['contact_email', 'email'])
                phone = _first_value(row, ['contact_phone', 'phone', 'mobile'])
                is_primary = _parse_bool(_first_value(row, ['is_primary', 'primary']))

                if not any([customer_email, contact_name, position, contact_email, phone]):
                    continue

                if not customer_email or not contact_name:
                    errors.append(
                        f'Row {row_num}: Customer Email and Contact Name are required'
                    )
                    continue

                candidates = Customer.objects.filter(email__iexact=customer_email)
                if not candidates.exists():
                    errors.append(f'Row {row_num}: Customer with email "{customer_email}" was not found')
                    continue

                customer = None
                if candidates.count() == 1:
                    customer = candidates.first()
                elif company_name:
                    customer = candidates.filter(company_name__iexact=company_name).first()

                if customer is None:
                    company_names = list(
                        candidates.values_list('company_name', flat=True)[:5]
                    )
                    suffix = '...' if candidates.count() > 5 else ''
                    errors.append(
                        f'Row {row_num}: Multiple customers found with email "{customer_email}". '
                        f'Include company_name to disambiguate. Matches: {", ".join(company_names)}{suffix}'
                    )
                    continue

                existing_contact = None
                if contact_email:
                    existing_contact = CustomerContact.objects.filter(
                        customer=customer,
                        email__iexact=contact_email,
                    ).first()

                if existing_contact is None:
                    existing_contact = CustomerContact.objects.filter(
                        customer=customer,
                        name__iexact=contact_name,
                    ).first()

                if existing_contact is None and customer.contacts.count() >= 4:
                    errors.append(
                        f'Row {row_num}: Customer "{customer.company_name}" already has 4 additional contacts'
                    )
                    continue

                try:
                    with transaction.atomic():
                        if existing_contact:
                            existing_contact.name = contact_name
                            existing_contact.position = position
                            existing_contact.email = contact_email or None
                            existing_contact.phone = phone
                            existing_contact.is_primary = is_primary
                            existing_contact.save()
                            updated_count += 1
                        else:
                            CustomerContact.objects.create(
                                customer=customer,
                                name=contact_name,
                                position=position,
                                email=contact_email or None,
                                phone=phone,
                                is_primary=is_primary,
                            )
                            created_count += 1
                except Exception as exc:
                    errors.append(f'Row {row_num}: Error saving contact - {exc}')

            if created_count or updated_count:
                messages.success(
                    request,
                    f'Customer contacts import complete. '
                    f'Created: {created_count}, Updated: {updated_count}.'
                )

            if errors:
                error_message = f'Encountered {len(errors)} errors:\n' + '\n'.join(errors[:10])
                if len(errors) > 10:
                    error_message += f'\n... and {len(errors) - 10} more errors.'
                messages.warning(request, error_message)

            if not created_count and not updated_count and not errors:
                messages.info(request, 'No contact rows were found to import.')

        except Exception as exc:
            messages.error(request, f'Error processing CSV file: {exc}')

        return redirect('import_customer_contacts')

    return render(request, 'customers/import_customer_contacts.html')


@login_required
@user_passes_test(is_admin)
def import_customers_with_contacts(request):
    """Import customers and up to 4 additional contacts from one CSV row per customer."""
    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            messages.error(request, 'Please select a CSV file to upload.')
            return redirect('import_customers_with_contacts')

        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'Please upload a valid CSV file.')
            return redirect('import_customers_with_contacts')

        try:
            decoded_text = _decode_csv_upload(csv_file)
            if decoded_text is None:
                messages.error(
                    request,
                    'Unable to read the CSV file. Please re-save it as "CSV UTF-8" and upload again.'
                )
                return redirect('import_customers_with_contacts')

            reader = csv.DictReader(io.StringIO(decoded_text))
            if not reader.fieldnames:
                messages.error(request, 'The CSV file is missing a header row.')
                return redirect('import_customers_with_contacts')

            detected_headers = [
                (header or '').strip()
                for header in reader.fieldnames
                if (header or '').strip()
            ]
            normalized_headers = [
                header.strip().lower().replace(' ', '_')
                for header in reader.fieldnames
                if (header or '').strip()
            ]

            imported_count = 0
            contact_count = 0
            errors = []

            for row_num, row in enumerate(reader, start=2):
                company_name = _first_csv_value(row, ['company_name', 'company'])
                contact_person_name = _first_csv_value(
                    row,
                    ['contact_person_name', 'primary_contact_name', 'main_contact_name'],
                )
                contact_person_position = _first_csv_value(
                    row,
                    ['contact_person_position', 'primary_contact_position', 'main_contact_position'],
                )
                email = _first_csv_value(row, ['email', 'customer_email', 'primary_contact_email'])
                phone_number = _first_csv_value(row, ['phone_number', 'phone', 'mobile', 'primary_contact_phone'])
                address = _first_csv_value(row, ['address'])
                industry = _first_csv_value(row, ['industry'])
                territory = _first_csv_value(row, ['territory'])
                active_status = _first_csv_value(row, ['active_status', 'is_active']) or 'Yes'
                salesperson_initials = _first_csv_value(
                    row,
                    ['salesperson_initials', 'salesperson', 'salesperson_username'],
                )

                if not any(row.values()):
                    continue

                if not company_name or not contact_person_name or not email:
                    missing_parts = []
                    if not company_name:
                        missing_parts.append('company_name')
                    if not contact_person_name:
                        missing_parts.append('contact_person_name')
                    if not email:
                        missing_parts.append('email')

                    errors.append(
                        f'Row {row_num}: Required customer fields could not be read '
                        f'({", ".join(missing_parts)}). '
                        f'Detected headers: {", ".join(detected_headers) or "none"}. '
                        f'Normalized headers: {", ".join(normalized_headers) or "none"}.'
                    )
                    continue

                if Customer.objects.filter(email__iexact=email, company_name__iexact=company_name).exists():
                    errors.append(
                        f'Row {row_num}: Customer "{company_name}" with email {email} already exists'
                    )
                    continue

                industry_value = _map_customer_choice(industry, Customer.INDUSTRY_CHOICES)
                if industry and industry_value is None:
                    errors.append(f'Row {row_num}: Invalid industry "{industry}"')
                    continue

                territory_value = _map_customer_choice(territory, Customer.TERRITORY_CHOICES)
                if territory and territory_value is None:
                    errors.append(f'Row {row_num}: Invalid territory "{territory}"')
                    continue

                is_active = _parse_csv_bool(active_status)

                salesperson = None
                if salesperson_initials:
                    salesperson = User.objects.filter(
                        initials__iexact=salesperson_initials,
                        role__in=['salesperson', 'supervisor', 'asm', 'sm', 'avp'],
                        is_active=True,
                    ).first()
                    if salesperson is None:
                        errors.append(
                            f'Row {row_num}: Active salesperson with initials "{salesperson_initials}" not found'
                        )
                        continue

                extra_contacts = []
                for index in range(2, 6):
                    extra_name = _first_csv_value(
                        row,
                        [f'contact_{index}_name', f'additional_contact_{index}_name'],
                    )
                    extra_position = _first_csv_value(
                        row,
                        [f'contact_{index}_position', f'additional_contact_{index}_position'],
                    )
                    extra_email = _first_csv_value(
                        row,
                        [f'contact_{index}_email', f'additional_contact_{index}_email'],
                    )
                    extra_phone = _first_csv_value(
                        row,
                        [f'contact_{index}_phone', f'contact_{index}_mobile', f'additional_contact_{index}_phone'],
                    )
                    extra_primary = _parse_csv_bool(
                        _first_csv_value(
                            row,
                            [f'contact_{index}_is_primary', f'additional_contact_{index}_is_primary'],
                        )
                    )

                    if not any([extra_name, extra_position, extra_email, extra_phone]):
                        continue

                    if not extra_name:
                        errors.append(f'Row {row_num}: Contact {index} name is required when other contact {index} fields are filled')
                        extra_contacts = None
                        break

                    extra_contacts.append({
                        'name': extra_name,
                        'position': extra_position,
                        'email': extra_email or None,
                        'phone': extra_phone,
                        'is_primary': extra_primary,
                    })

                if extra_contacts is None:
                    continue

                try:
                    with transaction.atomic():
                        customer = Customer.objects.create(
                            company_name=company_name,
                            contact_person_name=contact_person_name,
                            contact_person_position=contact_person_position,
                            email=email,
                            phone_number=phone_number,
                            address=address,
                            industry=industry_value or '',
                            territory=territory_value or '',
                            is_active=is_active,
                            salesperson=salesperson,
                        )

                        for contact_data in extra_contacts[:4]:
                            CustomerContact.objects.create(customer=customer, **contact_data)

                        imported_count += 1
                        contact_count += len(extra_contacts[:4])
                except Exception as exc:
                    errors.append(f'Row {row_num}: Error creating customer - {exc}')

            if imported_count > 0:
                messages.success(
                    request,
                    f'Successfully imported {imported_count} customers and {contact_count} additional contacts.',
                )

            if errors:
                error_message = f'Encountered {len(errors)} errors:\n' + '\n'.join(errors[:10])
                if len(errors) > 10:
                    error_message += f'\n... and {len(errors) - 10} more errors.'
                messages.warning(request, error_message)

            if not imported_count and not errors:
                messages.info(request, 'No customer rows were found to import.')

        except Exception as exc:
            messages.error(request, f'Error processing CSV file: {exc}')

        return redirect('import_customers_with_contacts')

    return render(request, 'customers/import_customers_with_contacts.html')

@login_required
@user_passes_test(is_admin)
def download_sample_csv(request):
    """Download a sample CSV template for customer import"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="customer_import_sample.csv"'
    
    writer = csv.writer(response)
    # Write header - matching export format
    writer.writerow([
        'Company Name', 'Contact Person Name', 'Contact Person Position', 'Email', 'Phone Number', 'Address', 
        'Industry', 'Territory', 'Millionaire Status', 'Active Status', 'Salesperson Initials',
        'Created At', 'Updated At'
    ])
    
    # Write sample data with correct choice values
    writer.writerow([
        'ABC Corporation', 'John Doe', 'CEO', 'john.doe@abccorp.com', '+1234567890', '123 Main St, Makati City, Metro Manila', 
        'Technology', 'Makati City', 'Yes', 'Yes', 'JDS',
        '2024-01-15 09:30:00', '2024-01-20 14:45:00'
    ])
    writer.writerow([
        'XYZ Industries', 'Jane Smith', 'Purchasing Manager', 'jane.smith@xyzind.com', '+0987654321', '456 Oak Ave, Pasig City, Metro Manila', 
        'Manufacturing', 'Pasig City', 'No', 'Yes', '',
        '2024-01-16 11:20:00', '2024-01-25 16:15:00'
    ])
    writer.writerow([
        'Global Tech Solutions', 'Michael Johnson', 'Finance Director', 'mjohnson@globaltech.com', '+1122334455', '789 Pine St, Ortigas Center, Metro Manila', 
        'Finance & Banking', 'Ortigas', 'Yes', 'No', 'MRP',
        '2024-01-17 08:15:00', '2024-01-30 10:30:00'
    ])
    
    return response


@login_required
@user_passes_test(is_admin)
def download_customer_contacts_sample_csv(request):
    """Download a sample CSV template for importing additional customer contacts."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="customer_contacts_import_sample.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'customer_email',
        'contact_name',
        'contact_position',
        'contact_email',
        'contact_phone',
        'is_primary',
    ])
    writer.writerow([
        'john.doe@abccorp.com',
        'Maria Santos',
        'Procurement Manager',
        'maria.santos@abccorp.com',
        '+639171112233',
        'Yes',
    ])
    writer.writerow([
        'john.doe@abccorp.com',
        'Peter Cruz',
        'IT Manager',
        'peter.cruz@abccorp.com',
        '+639181234567',
        'No',
    ])

    return response


@login_required
@user_passes_test(is_admin)
def download_customer_with_contacts_sample_csv(request):
    """Download a sample CSV template for importing customers with extra contacts in one file."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="customer_with_contacts_import_sample.csv"'

    writer = csv.writer(response)
    writer.writerow(_customer_with_contacts_header())
    writer.writerow([
        'ABC Corporation',
        'John Doe',
        'CEO',
        'john.doe@abccorp.com',
        '+1234567890',
        '123 Main St, Makati City, Metro Manila',
        'Technology',
        'Makati City',
        'Yes',
        'JDS',
        'Maria Santos',
        'Procurement Manager',
        'maria.santos@abccorp.com',
        '+639171112233',
        'No',
        'Peter Cruz',
        'IT Manager',
        'peter.cruz@abccorp.com',
        '+639181234567',
        'No',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
    ])
    writer.writerow([
        'XYZ Industries',
        'Jane Smith',
        'Purchasing Manager',
        'jane.smith@xyzind.com',
        '+0987654321',
        '456 Oak Ave, Pasig City, Metro Manila',
        'Manufacturing',
        'Pasig City',
        'Yes',
        '',
        'Anna Reyes',
        'Finance Officer',
        'anna.reyes@xyzind.com',
        '+639199998888',
        'Yes',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
    ])

    return response


@login_required
@user_passes_test(is_admin)
def toggle_customer_vip(request, pk):
    """Toggle customer VIP status (AJAX endpoint)"""
    if request.method == 'POST':
        try:
            customer = get_object_or_404(Customer, pk=pk)
            old_vip_status = customer.is_vip
            customer.is_vip = not customer.is_vip
            customer.save()
            
            # Log history event
            action = 'vip_enabled' if customer.is_vip else 'vip_disabled'
            description = f"Customer VIP status changed from {'VIP' if old_vip_status else 'Regular'} to {'VIP' if customer.is_vip else 'Regular'} by {request.user.get_full_name() or request.user.username}"
            
            history_entry = CustomerHistory(
                customer=customer,
                action=action,
                description=description,
                changed_by=request.user,
                salesperson_at_time=customer.salesperson,
                old_value={'is_vip': old_vip_status},
                new_value={'is_vip': customer.is_vip},
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
            )
            history_entry.save()
            
            return JsonResponse({
                'success': True,
                'message': f'{customer.full_name} VIP status updated.',
                'is_vip': customer.is_vip
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'message': 'Invalid request method.'})


@login_required
def customer_history(request, pk):
    """View complete history of a customer for tracking and salesperson attribution"""
    customer = get_object_or_404(Customer, pk=pk)
    
    # Check if user has permission to view this customer
    user = request.user
    has_access = False
    
    if user.role in ['admin', 'president', 'gm', 'vp', 'marketing']:
        has_access = True
    elif user.role == 'avp':
        teams = Team.objects.filter(avp=user)
        groups = Group.objects.filter(team__in=teams)
        salespeople_ids = TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)
        has_access = customer.salesperson_id in salespeople_ids or customer.salesperson_id == user.id
    elif user.role in ['asm', 'sm']:
        # Group-scoped: only customers within the groups the ASM/SM handles.
        from customers.permissions import group_scoped_member_ids
        has_access = customer.salesperson_id in group_scoped_member_ids(user)
    elif user.role == 'supervisor':
        groups = Group.objects.filter(supervisor=user)
        salespeople_ids = TeamMembership.objects.filter(group__in=groups).values_list('user_id', flat=True)
        has_access = customer.salesperson_id in salespeople_ids or customer.salesperson_id == user.id
    elif user.role == 'teamlead':
        teamlead_groups = Group.objects.filter(teamlead=user)
        salespeople_ids = TeamMembership.objects.filter(group__in=teamlead_groups).values_list('user_id', flat=True)
        has_access = customer.salesperson_id in salespeople_ids or customer.salesperson_id == user.id
    elif user.role == 'salesperson':
        has_access = customer.salesperson == user
    
    if not has_access:
        messages.error(request, 'You do not have permission to view this customer history.')
        return redirect('customer_list')
    
    # Get history records
    history = CustomerHistory.objects.filter(customer=customer).select_related(
        'changed_by', 'salesperson_at_time'
    ).order_by('-timestamp')
    
    # Get summary statistics
    history_stats = {
        'total_changes': history.count(),
        'vip_changes': history.filter(action__in=['vip_enabled', 'vip_disabled']).count(),
        'status_changes': history.filter(action__in=['activated', 'deactivated']).count(),
        'salesperson_changes': history.filter(action__in=['salesperson_assigned', 'salesperson_changed', 'salesperson_removed']).count(),
        'field_updates': history.filter(action='field_updated').count(),
    }
    
    # Show each attributed salesperson only once in the summary card.
    salesperson_ids = list(
        history.filter(salesperson_at_time__isnull=False)
        .values_list('salesperson_at_time_id', flat=True)
        .distinct()
    )
    salespeople_history = User.objects.filter(id__in=salesperson_ids).order_by(
        'first_name', 'last_name', 'username'
    )
    
    context = {
        'customer': customer,
        'history': history,
        'history_stats': history_stats,
        'salespeople_history': salespeople_history,
    }
    
    return render(request, 'customers/customer_history.html', context)


# =====================================================================
# ADMIN CUSTOMER MANAGEMENT & BACKUP/RESTORE FUNCTIONALITY
# =====================================================================

@login_required
def edit_customer(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    if not perms_can_edit_customer(request.user, customer):
        messages.error(request, "You don't have permission to edit this customer.")
        return redirect('customer_list')
    
    if request.method == 'POST':
        # Create backup before making changes
        customer.create_backup(
            changed_by=request.user,
            reason="Before edit"
        )
        
        if request.user.role == 'salesperson':
            form = SalespersonCustomerUpdateForm(request.POST, instance=customer)
        else:
            form = CustomerForm(request.POST, instance=customer, user=request.user)
        contact_formset = CustomerContactFormSet(request.POST, instance=customer)
        if form.is_valid() and contact_formset.is_valid():
            form.save()
            contacts = contact_formset.save()
            messages.success(request, f'Customer "{customer.full_name}" has been updated successfully. Backup created automatically.')
            return redirect('customer_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        if request.user.role == 'salesperson':
            form = SalespersonCustomerUpdateForm(instance=customer)
        else:
            form = CustomerForm(instance=customer, user=request.user)
        contact_formset = CustomerContactFormSet(instance=customer)
    
    # Get recent backups for this customer
    recent_backups = CustomerBackup.objects.filter(customer=customer)[:5]
    
    context = {
        'form': form,
        'customer': customer,
        'contact_formset': contact_formset,
        'recent_backups': recent_backups,
        'is_edit': True
    }
    
    return render(request, 'customers/customer_form.html', context)

@login_required
@user_passes_test(is_admin)
def create_delinquency(request):
    from .forms import DelinquencyCreateForm
    from .models import DelinquentCustomer, DelinquencyRecord
    if request.method == 'POST':
        form = DelinquencyCreateForm(request.POST)
        if form.is_valid():
            company = form.cleaned_data['company_name'].strip()
            assigned_ae = form.cleaned_data.get('assigned_ae') or ''
            email = (form.cleaned_data.get('email') or '').strip().lower()
            status = form.cleaned_data['status']
            tin = form.cleaned_data.get('tin_number') or ''
            partner = form.cleaned_data.get('partner_name') or ''
            date_delivered = form.cleaned_data.get('date_delivered')
            last_payment = form.cleaned_data.get('last_payment_date')
            remarks = form.cleaned_data.get('remarks') or ''
            dcustomer = DelinquentCustomer.objects.create(
                company_name=company,
                assigned_ae=assigned_ae,
                email=email
            )
            DelinquencyRecord.objects.create(
                customer=dcustomer,
                salesperson=None,
                status=status,
                tin_number=tin,
                partner_name=partner,
                date_delivered=date_delivered,
                last_payment_date=last_payment,
                remarks=remarks,
                created_by=request.user
            )
            messages.success(request, 'Delinquency record created.')
            return redirect('delinquent_list')
    else:
        form = DelinquencyCreateForm()
    return render(request, 'customers/delinquency_form.html', {'form': form, 'title': 'Add Delinquency Record'})

@login_required
@user_passes_test(is_admin)
def import_delinquencies(request):
    """Import delinquency records from CSV (Excel saved as CSV).
    Accepted columns (case-insensitive, flexible):
      - Company: company_name, company, company name
      - Email: email
      - Contact Person: contact_person, contact, contact person
      - TIN: tin_number, tin, tin number, tin no
      - Amount Due: amount_due, amount, balance, ar amount
      - Due Date: due_date, due, due date
      - Last Payment Date: last_payment_date, last payment, last payment date
      - Status: status (open|resolved|watch)
      - Remarks/Notes: remarks, notes
      - Salesperson: salesperson_username, salesperson, ae, collector, initials
    """
    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            messages.error(request, 'Please select a CSV file to upload.')
            return redirect('delinquent_list')
        try:
            import csv, io
            # Decode safely (preserves ñ; no silent corruption).
            decoded_text = decode_csv_bytes(csv_file.read())
            if decoded_text is None:
                messages.error(
                    request,
                    'Unable to read CSV. Please re-save it as "CSV UTF-8" and upload again.'
                )
                return redirect('delinquent_list')
            sio = io.StringIO(decoded_text)
            # Try to sniff delimiter if needed
            try:
                sample = decoded_text[:4096]
                dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
            except csv.Error:
                dialect = 'excel'
            sio.seek(0)
            reader = csv.DictReader(sio, dialect=dialect)
            created = 0
            from decimal import Decimal
            from django.utils.dateparse import parse_date
            from datetime import datetime

            def first_of(row, keys):
                for k in keys:
                    # try exact, lower, title
                    v = row.get(k) or row.get(k.lower()) or row.get(k.title())
                    if v not in [None, '']:
                        return v
                return ''

            def parse_amount(s):
                if s is None:
                    return Decimal('0')
                s = str(s).strip()
                s = s.replace('₱', '').replace(',', '').replace(' ', '')
                negative = False
                if s.startswith('(') and s.endswith(')'):
                    negative = True
                    s = s[1:-1]
                try:
                    val = Decimal(s)
                    return -val if negative else val
                except Exception:
                    return Decimal('0')

            def parse_date_flexible(s):
                if not s:
                    return None
                s = str(s).strip()
                # Try pandas-like excel serial?
                try:
                    # If it's a float-like excel serial number, skip here; left for future enhancement
                    pass
                except Exception:
                    pass
                # Try built-in ISO parser first
                d = parse_date(s)
                if d:
                    return d
                # Try a set of common formats (02/15/26, 15/02/2026, etc.)
                formats = ['%m/%d/%y','%m/%d/%Y','%d/%m/%y','%d/%m/%Y','%b %d %Y','%d-%b-%Y']
                for fmt in formats:
                    try:
                        return datetime.strptime(s, fmt).date()
                    except Exception:
                        continue
                return None

            for row in reader:
                company = first_of(row, ['company_name', 'company', 'Company Name'])
                email = first_of(row, ['email', 'Email'])
                assigned_ae_val = first_of(row, ['assigned_ae', 'Assigned AE', 'AE', 'Account Executive', 'contact_person', 'Contact Person'])
                remarks = first_of(row, ['remarks', 'notes', 'Remarks', 'Notes'])
                tin_number = first_of(row, ['tin_number', 'TIN', 'TIN Number', 'Tin No', 'Tin #'])
                partner_name = first_of(row, ['partner_name', 'Partners Name', 'Partner Name', 'Partner', 'Partner_Name'])
                status = (first_of(row, ['status', 'Status']) or 'open').lower()
                amount_str = first_of(row, ['amount_due', 'Amount Due', 'amount', 'Amount', 'balance', 'Balance', 'AR Amount'])
                date_delivered_str = first_of(row, ['date_delivered', 'date_deliver', 'Date Delivered', 'Date Deliver'])
                last_payment_str = first_of(row, ['last_payment_date', 'last_payment', 'Last Payment Date', 'Last Payment'])
                sp_val = first_of(row, ['salesperson_username', 'Salesperson Username', 'salesperson', 'Salesperson', 'ae', 'AE', 'collector', 'Collector', 'initials', 'Initials', 'Account Executive'])

                from decimal import Decimal
                amount = parse_amount(amount_str)
                date_delivered = parse_date_flexible(date_delivered_str) if date_delivered_str else None
                last_payment = parse_date_flexible(last_payment_str) if last_payment_str else None
                # Find or create delinquent customer (separate table)
                from .models import DelinquentCustomer
                dcustomer = None
                if email:
                    dcustomer = DelinquentCustomer.objects.filter(email__iexact=email).first()
                if not dcustomer and company:
                    dcustomer = DelinquentCustomer.objects.filter(company_name__iexact=company).first()
                if dcustomer and assigned_ae_val:
                    if (dcustomer.assigned_ae or '').strip().lower() in ['', 'unknown'] or dcustomer.assigned_ae != assigned_ae_val:
                        dcustomer.assigned_ae = assigned_ae_val
                        dcustomer.save(update_fields=['assigned_ae'])
                if not dcustomer and company:
                    dcustomer = DelinquentCustomer.objects.create(
                        company_name=company,
                        assigned_ae=assigned_ae_val or '',
                        email=email or ''
                    )
                # Find salesperson
                salesperson = None
                if sp_val:
                    # Try by username first
                    salesperson = User.objects.filter(username__iexact=sp_val, is_active=True).first()
                    # Fallback to initials match
                    if not salesperson:
                        salesperson = User.objects.filter(initials__iexact=sp_val, is_active=True).first()
                if dcustomer:
                    final_remarks = remarks
                    DelinquencyRecord.objects.create(
                        customer=dcustomer,
                        salesperson=salesperson,
                        status=status if status in ['open','resolved','watch'] else 'open',
                        tin_number=tin_number,
                        partner_name=partner_name,
                        date_delivered=date_delivered,
                        last_payment_date=last_payment,
                        remarks=final_remarks,
                        created_by=request.user
                    )
                    created += 1
            messages.success(request, f'Imported {created} delinquency records.')
            return redirect('delinquent_list')
        except Exception as e:
            messages.error(request, f'Import failed: {e}')
            return redirect('delinquent_list')
    return render(request, 'customers/delinquency_import.html', {'title': 'Import Delinquency Records'})

@login_required
@user_passes_test(is_admin)
def download_delinquency_sample_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="delinquency_sample.csv"'
    import csv
    writer = csv.writer(response)
    writer.writerow(['company_name','email','assigned_ae','tin_number','partner_name','date_delivered','last_payment_date','status','remarks','salesperson_username'])
    writer.writerow(['Acme Corp','billing@acme.com','J. Rabe','000-123-456','Micro Image','2026-02-15','2026-01-15','open','Hard to collect due to long processing','jsmith'])
    return response

@login_required
@user_passes_test(is_admin)
def export_delinquencies(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="delinquency_export.csv"'
    import csv
    writer = csv.writer(response)
    writer.writerow([
        'company_name','email','assigned_ae','tin_number','status','partner_name','date_delivered','last_payment_date','remarks','salesperson_username','created_by','updated_at'
    ])
    qs = DelinquencyRecord.objects.select_related('customer','salesperson','created_by').all().order_by('customer__company_name')
    for rec in qs:
        writer.writerow([
            rec.customer.company_name,
            rec.customer.email,
            rec.customer.assigned_ae,
            rec.tin_number or '',
            rec.get_status_display(),
            rec.partner_name or '',
            rec.date_delivered.isoformat() if rec.date_delivered else '',
            rec.last_payment_date.isoformat() if rec.last_payment_date else '',
            rec.remarks.replace('\n',' ').strip() if rec.remarks else '',
            rec.salesperson.username if rec.salesperson else '',
            rec.created_by.username if rec.created_by else '',
            rec.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
        ])
    return response
 
@login_required
@user_passes_test(is_admin)
def clear_delinquencies(request):
    if request.method == 'POST':
        count = DelinquencyRecord.objects.count()
        DelinquencyRecord.objects.all().delete()
        messages.success(request, f'Cleared {count} delinquency records.')
        return redirect('delinquent_list')
    return render(request, 'customers/confirm_clear_delinquencies.html', {})


@login_required
@user_passes_test(is_admin)
def customer_backups(request, pk):
    """View all backups for a specific customer"""
    customer = get_object_or_404(Customer, pk=pk)
    backups = CustomerBackup.objects.filter(customer=customer)
    
    context = {
        'customer': customer,
        'backups': backups
    }
    
    return render(request, 'customers/customer_backups.html', context)


@login_required
@user_passes_test(is_admin)
def create_manual_backup(request, pk):
    """Create a manual backup of customer data"""
    if request.method == 'POST':
        customer = get_object_or_404(Customer, pk=pk)
        reason = request.POST.get('reason', 'Manual backup by admin')
        
        try:
            backup = customer.create_backup(
                changed_by=request.user,
                reason=reason
            )
            messages.success(request, f'Manual backup created successfully for "{customer.full_name}".')
        except Exception as e:
            messages.error(request, f'Error creating backup: {str(e)}')
        
        return redirect('customer_backups', pk=pk)
    
    return redirect('customer_list')


@login_required
@user_passes_test(is_admin)
def restore_customer(request, customer_pk, backup_pk):
    """Restore customer from a specific backup"""
    customer = get_object_or_404(Customer, pk=customer_pk)
    backup = get_object_or_404(CustomerBackup, pk=backup_pk, customer=customer)
    
    if request.method == 'POST':
        try:
            backup.restore(restored_by=request.user)
            messages.success(
                request, 
                f'Customer "{customer.full_name}" has been restored from backup '
                f'created on {backup.created_at.strftime("%Y-%m-%d %H:%M:%S")}.'
            )
            return redirect('customer_list')
        except Exception as e:
            messages.error(request, f'Error restoring customer: {str(e)}')
            return redirect('customer_backups', pk=customer_pk)
    
    # Show confirmation page
    backup_data = backup.get_backup_data()
    context = {
        'customer': customer,
        'backup': backup,
        'backup_data': backup_data
    }
    
    return render(request, 'customers/restore_customer.html', context)


@login_required
@user_passes_test(is_admin)
def backup_overview(request):
    """Overview of all customer backups in the system"""
    # Get statistics
    total_customers = Customer.objects.count()
    total_backups = CustomerBackup.objects.count()
    customers_with_backups = Customer.objects.filter(backups__isnull=False).distinct().count()
    
    # Get recent backups across all customers
    recent_backups = CustomerBackup.objects.select_related('customer', 'changed_by').order_by('-created_at')[:20]
    
    # Get customers with most backups
    customers_by_backup_count = Customer.objects.annotate(
        backup_count=models.Count('backups')
    ).filter(backup_count__gt=0).order_by('-backup_count')[:10]
    
    # Calculate coverage percentage
    coverage_percent = 0
    if total_customers > 0:
        coverage_percent = round((customers_with_backups * 100) / total_customers)
    
    context = {
        'stats': {
            'total_customers': total_customers,
            'total_backups': total_backups,
            'customers_with_backups': customers_with_backups,
            'customers_without_backups': total_customers - customers_with_backups,
            'coverage_percent': coverage_percent,
        },
        'recent_backups': recent_backups,
        'customers_by_backup_count': customers_by_backup_count,
    }
    
    return render(request, 'customers/backup_overview.html', context)


@login_required
@user_passes_test(is_admin)
def toggle_customer_active(request, pk):
    """Toggle customer active status (AJAX endpoint)"""
    if request.method == 'POST':
        try:
            customer = get_object_or_404(Customer, pk=pk)
            old_active_status = customer.is_active
            customer.is_active = not customer.is_active
            customer.save()
            
            # Log history event
            action = 'activated' if customer.is_active else 'deactivated'
            description = f"Customer status changed from {'Active' if old_active_status else 'Inactive'} to {'Active' if customer.is_active else 'Inactive'} by {request.user.get_full_name() or request.user.username}"
            
            history_entry = CustomerHistory(
                customer=customer,
                action=action,
                description=description,
                changed_by=request.user,
                salesperson_at_time=customer.salesperson,
                old_value={'is_active': old_active_status},
                new_value={'is_active': customer.is_active},
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500]
            )
            history_entry.save()
            
            status = 'activated' if customer.is_active else 'deactivated'
            return JsonResponse({
                'success': True,
                'message': f'{customer.full_name} has been {status}.',
                'is_active': customer.is_active
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            })
    
    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

@login_required
def customer_detail(request, pk):
    """360-degree view of a customer"""
    customer = get_object_or_404(Customer, pk=pk)
    if not perms_can_view_customer(request.user, customer):
        messages.error(request, 'You do not have permission to view this customer.')
        return redirect('customer_list')
    
    # Gather Data
    active_deals = SalesFunnel.objects.filter(customer=customer).exclude(deal_outcome__in=['won', 'lost', 'cancelled'])
    all_deals = SalesFunnel.objects.filter(customer=customer).order_by('-created_at')
    won_deals = SalesFunnel.objects.filter(customer=customer, deal_outcome='won')
    
    proposals = Proposal.objects.filter(customer=customer).order_by('-created_at')
    
    # Get all activities for this customer
    all_activities = SalesActivity.objects.filter(customer=customer).select_related('activity_type', 'salesperson').order_by('-scheduled_start')
    recent_activities = all_activities[:5]
    
    # Get POCs
    pocs = ProofOfConcept.objects.filter(customer=customer).select_related('lead_engineer').order_by('-created_at')
    active_pocs_count = pocs.filter(status__in=['planned', 'ongoing']).count()
    
    # Get Tickets
    tickets = Ticket.objects.filter(customer=customer).select_related('assigned_to').order_by('-created_at')
    open_tickets_count = tickets.exclude(status__in=['resolved', 'closed', 'rejected']).count()
    
    # Get Notes
    notes = CustomerNote.objects.filter(customer=customer).select_related('author').order_by('-created_at')
    
    # Stats
    total_won_value = won_deals.aggregate(total=Sum('retail'))['total'] or 0
    
    context = {
        'customer': customer,
        'active_deals': active_deals,
        'all_deals': all_deals,
        'active_deals_count': active_deals.count(),
        'proposals': proposals,
        'activities': all_activities,
        'recent_activities': recent_activities,
        'pocs': pocs,
        'pocs_count': active_pocs_count,
        'tickets': tickets,
        'open_tickets_count': open_tickets_count,
        'notes': notes,
        'total_won_value': total_won_value,
        'can_edit': perms_can_edit_customer(request.user, customer),
    }
    return render(request, 'customers/customer_detail.html', context)
