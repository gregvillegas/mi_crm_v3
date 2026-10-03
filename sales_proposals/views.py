from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from .models import Proposal, ProposalItem, ProposalApprovalStep, ProposalApprovalTier, ProposalChangeLog, ProposalEmailLog
from .forms import ProposalForm, ProposalItemFormSet, ProposalApprovalTierForm, ProposalApprovalTierImportForm, ProposalAttachmentFormSet
import csv
import smtplib
import socket
from decimal import Decimal
from django.http import FileResponse
from django.conf import settings
import os
from customers.models import Customer
from users.models import User
from sales_monitoring.models import SalesActivity, ActivityType
from sales_funnel.models import SalesFunnel
from django.db import transaction
from django.db.models import F, Min, Q
from django.utils import timezone
from django.conf import settings
from django.template.loader import render_to_string
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io
from django.core.mail import EmailMultiAlternatives
import os
from pathlib import Path
from email.mime.image import MIMEImage

from reportlab.lib.utils import ImageReader


def _formset_has_valid_items(formset):
    """
    Return True if the ProposalItemFormSet contains at least one real line item
    (not deleted, not an empty extra form). Used to prevent saving an empty proposal.
    """
    for subform in formset.forms:
        if subform in getattr(formset, 'deleted_forms', []):
            continue
        cleaned = getattr(subform, 'cleaned_data', None)
        if not cleaned:
            continue
        if cleaned.get('DELETE'):
            continue
        # A real item must at least have a description or a unit price.
        if (cleaned.get('description') or '').strip() or cleaned.get('unit_price') is not None:
            return True
    return False


# Tokens that should stay UPPERCASE in a title-cased name/company/address
# (legal suffixes, common business acronyms, regional abbreviations).
_TITLE_KEEP_UPPER = {
    # Short legal-entity abbreviations conventionally written in caps.
    # NOTE: fully spelled-out words (Corporation, Incorporated, Company, Limited)
    # are intentionally NOT here — they should render in Title Case.
    'inc', 'corp', 'co', 'llc', 'ltd', 'plc', 'gmbh', 'sa', 'ph',
    'it', 'bpo', 'hr', 'usa', 'uk', 'un', 'ai',
    'ncr', 'ph.', 'inc.', 'corp.', 'co.', 'ltd.', 'jr', 'sr', 'ii', 'iii', 'iv',
}
# Short connector words that stay lowercase when NOT the first word
# (Filipino/Spanish/English name & place particles).
_TITLE_KEEP_LOWER = {
    'de', 'del', 'dela', 'la', 'las', 'los', 'y', 'da', 'di', 'van', 'von',
    'of', 'and', 'the', 'for', 'at', 'in', 'on', 'to', 'ng', 'sa',
}


def _smart_title_case(text):
    """
    Convert an ALL-CAPS (or all-lowercase) value to a clean Title Case for
    display, while preserving already well-cased values and common acronyms.

    - "JED CARMELI DE RAMOS"            -> "Jed Carmeli de Ramos"
    - "PRIMELINE PRODUCTS PHILIPPINES INC" -> "Primeline Products Philippines INC"
    - "LEVEL 3, SOHO CENTRAL CONDOMINIUM SHAW BOULEVARD"
                                        -> "Level 3, Soho Central Condominium Shaw Boulevard"
    - "John Iris Latupan" (already mixed case) -> returned unchanged

    Only reformats values that are effectively all-uppercase or all-lowercase,
    so hand-formatted mixed-case entries are never disturbed.
    """
    if not text:
        return text

    stripped = text.strip()
    if not stripped:
        return text

    # Only act on values that carry no intentional mixed-casing:
    # act if the text is all-caps, or has no lowercase-followed-by-uppercase
    # (i.e. it's uniformly cased). This leaves "John Iris Latupan" alone.
    letters = [c for c in stripped if c.isalpha()]
    if not letters:
        return text
    has_upper = any(c.isupper() for c in letters)
    has_lower = any(c.islower() for c in letters)
    is_all_caps = has_upper and not has_lower
    is_all_lower = has_lower and not has_upper
    if not (is_all_caps or is_all_lower):
        # Mixed case already — assume it's intentional; leave as-is.
        return stripped

    def _cap_word(word, is_first):
        if not word:
            return word
        low = word.lower()
        # Preserve acronyms/suffixes as uppercase
        core = low.strip('.,')
        if core in _TITLE_KEEP_UPPER:
            return word.upper()
        # Connectors stay lowercase unless they lead the phrase
        if not is_first and core in _TITLE_KEEP_LOWER:
            return low
        # Words containing digits (e.g. "3rd", "g1i") -> lowercase-ish, capitalize first alpha
        # Default: capitalize first letter, lowercase the rest
        return low[:1].upper() + low[1:]

    result_lines = []
    for line in stripped.split('\n'):
        out_tokens = []
        # Split on spaces but keep punctuation attached to words
        for idx, token in enumerate(line.split(' ')):
            if not token:
                out_tokens.append(token)
                continue
            # Handle hyphenated pieces individually (e.g. "SALCEDO-DELA")
            if '-' in token:
                sub = token.split('-')
                token_cased = '-'.join(
                    _cap_word(s, is_first=(idx == 0 and i == 0)) for i, s in enumerate(sub)
                )
            else:
                token_cased = _cap_word(token, is_first=(idx == 0))
            out_tokens.append(token_cased)
        result_lines.append(' '.join(out_tokens))
    return '\n'.join(result_lines)


def _resolve_email_signature_asset(filename):
    candidate_dirs = [
        Path(settings.BASE_DIR) / 'templates' / 'core' / 'static' / 'core' / 'images' / 'email_signature',
        Path(settings.BASE_DIR) / 'core' / 'static' / 'core' / 'images' / 'email_signature',
        Path(settings.BASE_DIR) / 'static' / 'core' / 'images' / 'email_signature',
        Path(settings.BASE_DIR),
    ]
    for directory in candidate_dirs:
        asset_path = directory / filename
        if asset_path.exists():
            return asset_path
    return None


def _get_proposal_email_signature_context(user):
    inline_images = []

    def register_inline_asset(cid, *filenames):
        for filename in filenames:
            image_path = _resolve_email_signature_asset(filename)
            if image_path:
                inline_images.append({
                    'cid': cid,
                    'path': image_path,
                })
                return cid
        return ''

    social_links = []
    social_settings = [
        (
            'Facebook',
            getattr(settings, 'COMPANY_FACEBOOK_URL', ''),
            'signature-facebook-icon',
            ('Facebook - FB.png', 'FB.png'),
        ),
        (
            'Instagram',
            getattr(settings, 'COMPANY_INSTAGRAM_URL', ''),
            'signature-instagram-icon',
            ('Instagram - IG.png', 'IG.png'),
        ),
        (
            'Twitter',
            getattr(settings, 'COMPANY_X_URL', ''),
            'signature-twitter-icon',
            ('Twitter - TWITT.png', 'TWITT.png'),
        ),
        (
            'Website',
            getattr(settings, 'COMPANY_WEBSITE_URL', 'https://www.microimageph.com'),
            'signature-website-icon',
            ('Website - WEB-ICON.png', 'WEB-ICON.png'),
        ),
    ]
    for label, url, icon_cid, filenames in social_settings:
        url = (url or '').strip()
        if url:
            social_links.append({
                'label': label,
                'url': url,
                'icon_cid': register_inline_asset(icon_cid, *filenames),
            })

    job_title = ''
    if getattr(user, 'job_title', ''):
        job_title = user.get_job_title_display()
    elif getattr(user, 'role', ''):
        job_title = user.get_role_display()

    return {
        'salesperson_name': user.get_full_name() or user.username,
        'salesperson_job_title': job_title,
        'salesperson_email': user.email or settings.DEFAULT_FROM_EMAIL,
        'salesperson_mobile': getattr(user, 'mobile_number', '') or '',
        'company_name': getattr(settings, 'COMPANY_NAME', 'Micro Image International Corp.'),
        'company_office_phone': getattr(settings, 'COMPANY_OFFICE_PHONE', '8-840-4323'),
        'company_address': getattr(
            settings,
            'COMPANY_ADDRESS',
            'Unit 53, 62 & 101 Legaspi Suites Building, 178 Salcedo St., '
            'Legaspi Village, Makati City 1229',
        ),
        'company_website_url': getattr(settings, 'COMPANY_WEBSITE_URL', 'https://www.microimageph.com'),
        'company_website_label': getattr(settings, 'COMPANY_WEBSITE_LABEL', 'www.microimageph.com'),
        'company_website_icon_cid': next(
            (
                item['icon_cid']
                for item in social_links
                if item['label'] == 'Website' and item['icon_cid']
            ),
            '',
        ),
        'company_social_links': social_links,
        'anniversary_image_cid': register_inline_asset('company-28-years', '28Years.png'),
        'inline_images': inline_images,
    }


def _build_proposal_email_text(cover_message, signature_context):
    lines = [cover_message.strip()]
    lines.extend([
        '',
        '--',
        signature_context['salesperson_name'],
    ])
    if signature_context['salesperson_job_title']:
        lines.append(signature_context['salesperson_job_title'])
    if signature_context['salesperson_mobile']:
        lines.append(f"Mobile: {signature_context['salesperson_mobile']}")
    if signature_context['salesperson_email']:
        lines.append(f"Email: {signature_context['salesperson_email']}")
    lines.extend([
        f"Office: {signature_context['company_office_phone']}",
        signature_context['company_address'],
        signature_context['company_website_label'],
    ])
    if signature_context['company_social_links']:
        social_text = ', '.join(
            f"{item['label']}: {item['url']}"
            for item in signature_context['company_social_links']
        )
        lines.append(f"Socials: {social_text}")
    return '\n'.join(line for line in lines if line is not None)


def _attach_inline_image(email_message, cid, image_path):
    image_path = Path(image_path)
    if not image_path.exists():
        return False

    subtype = image_path.suffix.lower().lstrip('.') or None
    with image_path.open('rb') as image_file:
        image = MIMEImage(image_file.read(), _subtype=subtype)
    image.add_header('Content-ID', f'<{cid}>')
    image.add_header('Content-Disposition', 'inline', filename=image_path.name)
    email_message.attach(image)
    return True


def notify_pending_approver(proposal, request=None):
    """
    Email the CURRENT pending approver (e.g. the AVP) that a proposal is waiting
    for their decision. Called when a proposal enters the approval workflow and
    each time it advances to the next approver.

    Fail-safe: never raises — a mail failure must not block the save/approval.
    Returns True if an email was sent, False otherwise.
    """
    try:
        if not proposal or not proposal.approval_required:
            return False
        if proposal.approval_status not in ('pending', 'in_progress'):
            return False

        step = proposal.get_current_pending_step()
        if not step or not step.approver:
            return False

        approver = step.approver
        to_email = (getattr(approver, 'email', '') or '').strip()
        if not to_email:
            return False

        creator = proposal.created_by
        creator_name = (creator.get_full_name() or creator.username) if creator else 'A salesperson'
        approver_name = approver.get_full_name() or approver.username
        currency_symbol = '₱' if proposal.currency == 'PHP' else '$'
        amount = proposal.total_amount or 0
        php_amount = proposal.approval_total_php or 0

        # Build a link to the proposal detail page.
        site_url = getattr(settings, 'SITE_URL', '').rstrip('/')
        try:
            from django.urls import reverse
            path = reverse('proposal_detail', args=[proposal.pk])
        except Exception:
            path = f'/proposals/{proposal.pk}/'
        if request is not None:
            proposal_url = request.build_absolute_uri(path)
        else:
            proposal_url = f'{site_url}{path}' if site_url else path

        subject = f'[Approval Needed] Proposal {proposal.proposal_number} — {proposal.customer.company_name}'

        body_lines = [
            f'Hi {approver_name},',
            '',
            f'A sales proposal is awaiting your approval (Level {step.level}).',
            '',
            f'  Proposal #: {proposal.proposal_number}',
            f'  Reference : {proposal.reference_number or "—"}',
            f'  Customer  : {proposal.customer.company_name}',
            f'  Subject   : {proposal.subject}',
            f'  Prepared by: {creator_name}',
            f'  Amount    : {currency_symbol}{amount:,.2f}'
            + (f' (≈ ₱{php_amount:,.2f})' if proposal.currency != 'PHP' else ''),
            '',
            f'Review and decide here: {proposal_url}',
            '',
            'You can also open the Approvals Inbox in the CRM to act on this request.',
            '',
            '— Micro Image CRM (automated notification)',
        ]
        body = '\n'.join(body_lines)

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'no-reply@microimageph.com'
        email = EmailMultiAlternatives(subject, body, from_email, [to_email])
        email.send(fail_silently=True)
        return True
    except Exception:
        # Notifications are best-effort; swallow all errors.
        return False


def notify_creator_of_decision(proposal, decision, decided_by=None, comment='', request=None):
    """
    Email the proposal creator (salesperson) when their proposal has been
    APPROVED or REJECTED.

    decision: 'approved' or 'rejected'.
    Fail-safe: never raises — a mail failure must not block the decision.
    Returns True if an email was sent, False otherwise.
    """
    try:
        if decision not in ('approved', 'rejected'):
            return False
        if not proposal:
            return False

        creator = proposal.created_by
        to_email = (getattr(creator, 'email', '') or '').strip()
        if not to_email:
            return False

        creator_name = creator.get_full_name() or creator.username
        decider_name = ''
        if decided_by:
            decider_name = decided_by.get_full_name() or decided_by.username
        currency_symbol = '₱' if proposal.currency == 'PHP' else '$'
        amount = proposal.total_amount or 0

        # Build a link to the proposal detail page.
        site_url = getattr(settings, 'SITE_URL', '').rstrip('/')
        try:
            from django.urls import reverse
            path = reverse('proposal_detail', args=[proposal.pk])
        except Exception:
            path = f'/proposals/{proposal.pk}/'
        if request is not None:
            proposal_url = request.build_absolute_uri(path)
        else:
            proposal_url = f'{site_url}{path}' if site_url else path

        if decision == 'approved':
            headline = 'has been APPROVED'
            subject = f'[Approved] Proposal {proposal.proposal_number} — {proposal.customer.company_name}'
            next_line = 'You may now send this proposal to the customer.'
        else:
            headline = 'has been REJECTED'
            subject = f'[Rejected] Proposal {proposal.proposal_number} — {proposal.customer.company_name}'
            next_line = 'Please review the feedback, make the necessary changes, and resubmit.'

        body_lines = [
            f'Hi {creator_name},',
            '',
            f'Your sales proposal {headline}'
            + (f' by {decider_name}.' if decider_name else '.'),
            '',
            f'  Proposal #: {proposal.proposal_number}',
            f'  Reference : {proposal.reference_number or "—"}',
            f'  Customer  : {proposal.customer.company_name}',
            f'  Subject   : {proposal.subject}',
            f'  Amount    : {currency_symbol}{amount:,.2f}',
        ]
        if comment:
            label = 'Comment' if decision == 'approved' else 'Reason'
            body_lines += ['', f'  {label}: {comment}']
        body_lines += [
            '',
            next_line,
            '',
            f'View the proposal here: {proposal_url}',
            '',
            '— Micro Image CRM (automated notification)',
        ]
        body = '\n'.join(body_lines)

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or 'no-reply@microimageph.com'
        email = EmailMultiAlternatives(subject, body, from_email, [to_email])
        email.send(fail_silently=True)
        return True
    except Exception:
        return False

def visible_proposals_queryset(user):
    """
    Return the proposals a user is allowed to see, scoped by role. Proposals are
    scoped by their author (`created_by`). Centralized here so the proposal list
    and global search share one source of truth for visibility.
    """
    if not getattr(user, 'is_authenticated', False):
        return Proposal.objects.none()

    if user.role == 'salesperson':
        return Proposal.objects.filter(created_by=user)

    if user.role == 'supervisor':
        managed_groups = user.managed_groups.all()
        member_ids = []
        for group in managed_groups:
            member_ids.extend(group.members.values_list('user_id', flat=True))
        member_ids.append(user.id)
        return Proposal.objects.filter(created_by_id__in=member_ids)

    if user.role == 'avp':
        managed_teams = user.managed_teams.all()
        member_ids = []
        for team in managed_teams:
            for group in team.groups.all():
                member_ids.extend(group.members.values_list('user_id', flat=True))
                if group.supervisor:
                    member_ids.append(group.supervisor.id)
                member_ids.extend(group.sm_managers.values_list('id', flat=True))
            if team.asm:
                member_ids.append(team.asm.id)
        member_ids.append(user.id)
        return Proposal.objects.filter(created_by_id__in=member_ids)

    if user.role == 'asm':
        # ASM sees proposals only from the groups they handle, with a fallback to
        # the whole team when no groups are assigned (shared asm_scoped_groups()).
        from teams.models import asm_scoped_groups
        asm_groups = asm_scoped_groups(user)
        member_ids = []
        for group in asm_groups:
            member_ids.extend(group.members.values_list('user_id', flat=True))
            if group.supervisor:
                member_ids.append(group.supervisor.id)
        member_ids.append(user.id)
        return Proposal.objects.filter(created_by_id__in=member_ids)

    if user.role == 'sm':
        # SM sees proposals from their specifically assigned groups only.
        from teams.models import Group, TeamMembership
        sm_groups = user.sm_groups.all()
        member_ids = list(TeamMembership.objects.filter(group__in=sm_groups).values_list('user_id', flat=True))
        supervisor_ids = list(
            Group.objects.filter(id__in=sm_groups.values_list('id', flat=True), supervisor__isnull=False)
            .values_list('supervisor_id', flat=True)
        )
        member_ids.extend(supervisor_ids)
        member_ids.append(user.id)
        return Proposal.objects.filter(created_by_id__in=member_ids)

    if user.role == 'teamlead':
        led_groups = user.led_groups.all()
        member_ids = []
        for group in led_groups:
            member_ids.extend(group.members.values_list('user_id', flat=True))
        member_ids.append(user.id)
        return Proposal.objects.filter(created_by_id__in=member_ids)

    # Admins, VPs, GMs, president see all
    return Proposal.objects.all()


def _apply_proposal_list_filters(request, proposals):
    """
    Apply the proposal-list GET filters (salesperson, month, team, group,
    format) to an already role-scoped proposals queryset. Shared by the list
    view and the Excel export so both reflect the same selection.
    """
    salesperson_id = request.GET.get('salesperson')
    if salesperson_id:
        try:
            proposals = proposals.filter(created_by_id=int(salesperson_id))
        except (ValueError, TypeError):
            pass

    selected_month = request.GET.get('month')
    if selected_month:
        try:
            year, month = map(int, selected_month.split('-'))
            proposals = proposals.filter(date__year=year, date__month=month)
        except (ValueError, TypeError):
            pass

    from teams.models import asm_scoped_groups
    selected_team = request.GET.get('team') or ''
    selected_group = request.GET.get('group') or ''

    if request.user.role in ['admin', 'gm', 'vp', 'president', 'avp']:
        if selected_team:
            try:
                proposals = proposals.filter(created_by__team_membership__group__team_id=int(selected_team))
            except (ValueError, TypeError):
                pass
        if selected_group:
            try:
                proposals = proposals.filter(created_by__team_membership__group_id=int(selected_group))
            except (ValueError, TypeError):
                pass
    elif request.user.role in ['asm', 'sm']:
        if request.user.role == 'asm':
            allowed_group_ids = set(asm_scoped_groups(request.user).values_list('id', flat=True))
        else:
            allowed_group_ids = set(request.user.sm_groups.values_list('id', flat=True))
        if selected_group:
            try:
                if int(selected_group) in allowed_group_ids:
                    proposals = proposals.filter(created_by__team_membership__group_id=int(selected_group))
            except (ValueError, TypeError):
                pass

    selected_format = request.GET.get('format') or ''
    if selected_format == 'multi':
        proposals = proposals.filter(is_multi_option=True)
    elif selected_format == 'single':
        proposals = proposals.filter(is_multi_option=False)

    return proposals


@login_required
def export_proposals_excel(request):
    """
    Export the (role-scoped, filtered) proposals to an Excel workbook.
    Restricted to Admin, AVP, and Sales Manager (asm/sm).
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    if request.user.role not in ['admin', 'avp', 'asm', 'sm']:
        messages.error(request, 'You are not authorized to export proposals.')
        return redirect('proposal_list')

    proposals = _apply_proposal_list_filters(
        request, visible_proposals_queryset(request.user)
    ).select_related('customer', 'created_by').order_by('-date', '-created_at')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Proposals'

    headers = [
        'Proposal #', 'Reference #', 'Subject', 'Customer', 'Date',
        'Currency', 'Amount', 'Amount (PHP)', 'Status', 'Approval Status',
        'Account Manager', 'Format',
    ]
    header_fill = PatternFill(start_color='A11313', end_color='A11313', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF')
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')

    row_idx = 2
    for p in proposals:
        am = p.created_by
        am_name = (am.get_full_name() or am.username) if am else ''
        ws.cell(row=row_idx, column=1, value=p.proposal_number)
        ws.cell(row=row_idx, column=2, value=p.reference_number or '')
        ws.cell(row=row_idx, column=3, value=p.subject)
        ws.cell(row=row_idx, column=4, value=p.customer.company_name if p.customer_id else '')
        ws.cell(row=row_idx, column=5, value=p.date.strftime('%Y-%m-%d') if p.date else '')
        ws.cell(row=row_idx, column=6, value=p.currency)
        ws.cell(row=row_idx, column=7, value=float(p.quoted_total_amount))
        ws.cell(row=row_idx, column=8, value=float(p.quoted_amount_php))
        ws.cell(row=row_idx, column=9, value=p.get_status_display())
        ws.cell(row=row_idx, column=10, value=p.get_approval_status_display())
        ws.cell(row=row_idx, column=11, value=am_name)
        ws.cell(row=row_idx, column=12, value='Multi-Option' if p.is_multi_option else 'Single')
        row_idx += 1

    # Reasonable column widths.
    widths = [16, 16, 40, 32, 12, 10, 16, 16, 12, 16, 24, 14]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = 'A2'

    from django.utils import timezone as _tz
    stamp = _tz.localdate().strftime('%Y%m%d')
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="proposals_export_{stamp}.xlsx"'
    wb.save(response)
    return response


@login_required
def proposal_list(request):
    proposals = visible_proposals_queryset(request.user)
    
    # Get list of salespeople for filter dropdown (from the visible proposals)
    salespeople_ids = proposals.values_list('created_by', flat=True).distinct()
    salespeople = User.objects.filter(id__in=salespeople_ids).order_by('first_name', 'last_name')
    
    # Filter by salesperson if requested
    salesperson_id = request.GET.get('salesperson')
    if salesperson_id:
        try:
            salesperson_id = int(salesperson_id)
            proposals = proposals.filter(created_by_id=salesperson_id)
        except ValueError:
            salesperson_id = None
            
    # Filter by Month if requested
    selected_month = request.GET.get('month')
    if selected_month:
        try:
            # selected_month format: YYYY-MM
            year, month = map(int, selected_month.split('-'))
            proposals = proposals.filter(date__year=year, date__month=month)
        except ValueError:
            selected_month = None

    # --- Team / Group granular filters ---
    # Path: Proposal.created_by -> TeamMembership.group -> Group.team
    #
    # Two audiences:
    #   * Execs + AVP  -> BOTH a Team and a Group dropdown (broad scope).
    #   * ASM + SM      -> ONLY a Group dropdown, limited to the groups THEY handle
    #                      (option A). The selected group is validated against that
    #                      allowed set so a hand-typed ?group= can't widen the view.
    from teams.models import Team as _TeamModel, Group as _GroupModel, asm_scoped_groups
    show_team_group_filters = request.user.role in ['admin', 'gm', 'vp', 'president', 'avp']
    show_group_filter = request.user.role in ['asm', 'sm']
    selected_team = request.GET.get('team') or ''
    selected_group = request.GET.get('group') or ''
    available_teams = []
    available_groups = []

    if show_team_group_filters:
        if selected_team:
            try:
                proposals = proposals.filter(
                    created_by__team_membership__group__team_id=int(selected_team)
                )
            except (ValueError, TypeError):
                selected_team = ''
        if selected_group:
            try:
                proposals = proposals.filter(
                    created_by__team_membership__group_id=int(selected_group)
                )
            except (ValueError, TypeError):
                selected_group = ''

        # Scope dropdown options: AVP sees only their managed teams; execs see all
        if request.user.role == 'avp':
            avp_team_ids = list(request.user.managed_teams.values_list('id', flat=True))
            available_teams = _TeamModel.objects.filter(id__in=avp_team_ids).order_by('name')
            available_groups = (
                _GroupModel.objects.select_related('team')
                .filter(team_id__in=avp_team_ids).order_by('team__name', 'name')
            )
        else:
            available_teams = _TeamModel.objects.all().order_by('name')
            available_groups = _GroupModel.objects.select_related('team').all().order_by('team__name', 'name')

    elif show_group_filter:
        # Group dropdown limited to the manager's OWN handled groups.
        if request.user.role == 'asm':
            allowed_groups = asm_scoped_groups(request.user)
        else:  # sm
            allowed_groups = request.user.sm_groups.all()
        allowed_group_ids = set(allowed_groups.values_list('id', flat=True))
        available_groups = (
            _GroupModel.objects.select_related('team')
            .filter(id__in=allowed_group_ids).order_by('team__name', 'name')
        )
        # Apply the group filter only if the chosen group is within the allowed set.
        if selected_group:
            try:
                if int(selected_group) in allowed_group_ids:
                    proposals = proposals.filter(
                        created_by__team_membership__group_id=int(selected_group)
                    )
                else:
                    selected_group = ''
            except (ValueError, TypeError):
                selected_group = ''

    # --- Format filter (single vs multi-option) ---
    selected_format = request.GET.get('format') or ''
    if selected_format == 'multi':
        proposals = proposals.filter(is_multi_option=True)
    elif selected_format == 'single':
        proposals = proposals.filter(is_multi_option=False)

    # Calculate Total Value of filtered proposals (in PHP)
    total_proposals_value = 0
    for proposal in proposals:
        total_proposals_value += proposal.quoted_amount_php

    # Group by Team for Executive Roles
    grouped_proposals = []
    show_team_grouping = False
    
    if request.user.role in ['admin', 'president', 'asm', 'sm', 'vp', 'avp', 'gm']:
        show_team_grouping = True
        
        # Optimize query by prefetching related team info
        proposals = proposals.select_related('created_by__team_membership__group__team')
        
        teams_dict = {}
        
        for proposal in proposals:
            team_name = "Unassigned"
            try:
                if hasattr(proposal.created_by, 'team_membership'):
                    group = proposal.created_by.team_membership.group
                    if group and group.team:
                        team_name = group.team.name
            except Exception:
                pass
            # Fallback for SM: resolve team via sm_groups
            if team_name == "Unassigned" and proposal.created_by.role == 'sm':
                try:
                    sm_group = proposal.created_by.sm_groups.select_related('team').first()
                    if sm_group and sm_group.team:
                        team_name = sm_group.team.name
                except Exception:
                    pass
            # Fallback for ASM: resolve team via asm_teams
            if team_name == "Unassigned" and proposal.created_by.role == 'asm':
                try:
                    from teams.models import Team as _Team
                    asm_team = _Team.objects.filter(asm=proposal.created_by).first()
                    if asm_team:
                        team_name = asm_team.name
                except Exception:
                    pass
            # Fallback for Supervisor: resolve team via managed_groups
            if team_name == "Unassigned" and proposal.created_by.role == 'supervisor':
                try:
                    sup_group = proposal.created_by.managed_groups.select_related('team').first()
                    if sup_group and sup_group.team:
                        team_name = sup_group.team.name
                except Exception:
                    pass

            # For SM viewing their own proposals: label as "On behalf" instead of team name
            if request.user.role == 'sm' and proposal.created_by_id == request.user.id:
                team_name = "On behalf"
            
            if team_name not in teams_dict:
                teams_dict[team_name] = {
                    'name': team_name,
                    'proposals': [],
                    'total_investment': 0
                }
            
            teams_dict[team_name]['proposals'].append(proposal)
            
            # Calculate PHP equivalent for total
            teams_dict[team_name]['total_investment'] += proposal.quoted_amount_php
            
        # Convert to list and sort
        grouped_proposals = list(teams_dict.values())
        # Sort by number of proposals (descending), then by team name
        grouped_proposals.sort(key=lambda x: (-len(x['proposals']), x['name']))

    # Get unique months for filter dropdown
    proposal_months = Proposal.objects.dates('date', 'month', order='DESC')
    
    context = {
        'proposals': proposals,
        'salespeople': salespeople,
        'selected_salesperson': salesperson_id,
        'proposal_months': proposal_months,
        'selected_month': selected_month,
        'total_proposals_value': total_proposals_value,
        'show_team_grouping': show_team_grouping,
        'grouped_proposals': grouped_proposals,
        'show_team_group_filters': show_team_group_filters,
        'show_group_filter': show_group_filter,
        'available_teams': available_teams,
        'available_groups': available_groups,
        'selected_team': selected_team,
        'selected_group': selected_group,
        'selected_format': selected_format,
    }
    
    return render(request, 'sales_proposals/proposal_list.html', context)

@login_required
def proposal_create(request):
    customer_id = request.GET.get('customer')
    customer = None
    if customer_id:
        customer = get_object_or_404(Customer, pk=customer_id)

    if request.method == 'POST':
        form = ProposalForm(request.POST, user=request.user)
        formset = ProposalItemFormSet(request.POST)
        attach_formset = ProposalAttachmentFormSet(request.POST, request.FILES)
        forms_valid = form.is_valid() and formset.is_valid() and attach_formset.is_valid()
        has_items = _formset_has_valid_items(formset) if formset.is_valid() else False
        if forms_valid and not has_items:
            messages.error(request, 'A proposal must have at least one item.')
        if forms_valid and has_items:
            with transaction.atomic():
                proposal = form.save(commit=False)
                proposal.created_by = request.user
                proposal.save()

                use_avail = proposal.use_availability_column
                _ = formset.save(commit=False)
                for subform in formset.forms:
                    if subform in formset.deleted_forms:
                        continue
                    if not subform.cleaned_data:
                        continue
                    if subform.empty_permitted and not any(
                        v for k, v in subform.cleaned_data.items()
                        if k != 'id' and v not in (None, '', False)
                    ):
                        continue
                    item = subform.save(commit=False)
                    item.proposal = proposal
                    form_value = (subform.cleaned_data.get('warranty') or '').strip()
                    if use_avail:
                        item.availability = form_value
                        item.warranty = ''
                    else:
                        item.warranty = form_value
                        item.availability = ''
                    item.save()
                for obj in formset.deleted_objects:
                    if getattr(obj, 'pk', None):
                        obj.delete()
                # Save attachments
                attachments = attach_formset.save(commit=False)
                for att in attachments:
                    att.proposal = proposal
                    att.uploaded_by = request.user
                    att.save()

                proposal.calculate_totals()
                proposal.ensure_approval_chain()

                # Auto-update Sales Funnel
                update_sales_funnel(proposal)

                # Notify the first pending approver (e.g. AVP), if approval is required.
                notify_pending_approver(proposal, request=request)

                messages.success(request, 'Proposal created successfully.')
                return redirect('proposal_detail', pk=proposal.pk)
    else:
        initial_data = {}
        if customer:
            initial_data['customer'] = customer
            
        form = ProposalForm(initial=initial_data, user=request.user)
        formset = ProposalItemFormSet()
        attach_formset = ProposalAttachmentFormSet()
    
    return render(request, 'sales_proposals/proposal_form.html', {
        'form': form,
        'formset': formset,
        'attach_formset': attach_formset,
        'title': 'Create Proposal',
        'customer': customer,
        'proposal': None,
    })

@login_required
def proposal_update(request, pk):
    proposal = get_object_or_404(Proposal, pk=pk)
    if request.method == 'POST':
        form = ProposalForm(request.POST, instance=proposal, user=request.user)
        formset = ProposalItemFormSet(request.POST, instance=proposal)
        attach_formset = ProposalAttachmentFormSet(request.POST, request.FILES, instance=proposal)
        forms_valid = form.is_valid() and formset.is_valid() and attach_formset.is_valid()
        has_items = _formset_has_valid_items(formset) if formset.is_valid() else False
        if forms_valid and not has_items:
            messages.error(request, 'A proposal must have at least one item.')
        if forms_valid and has_items:
            with transaction.atomic():
                before = Proposal.objects.get(pk=proposal.pk)
                before_approval_version = before.approval_version
                before_use_avail = before.use_availability_column
                before_items = {
                    i.pk: {
                        'part_number': i.part_number,
                        'description': i.description,
                        'quantity': str(i.quantity),
                        'unit_cost': str(i.unit_cost),
                        'unit_price': str(i.unit_price),
                        'column_value': (i.availability if before_use_avail else i.warranty) or '',
                        'use_availability_column': before_use_avail,
                        'is_optional': i.is_optional,
                        'is_bundle': i.is_bundle,
                        'bundled_items': i.bundled_items,
                    }
                    for i in before.items.all()
                }
                updated = form.save()
                use_avail = proposal.use_availability_column
                _ = formset.save(commit=False)
                for subform in formset.forms:
                    if subform in formset.deleted_forms:
                        continue
                    if not subform.cleaned_data:
                        continue
                    if subform.empty_permitted and not any(
                        v for k, v in subform.cleaned_data.items()
                        if k != 'id' and v not in (None, '', False)
                    ):
                        continue
                    item = subform.save(commit=False)
                    item.proposal = proposal
                    form_value = (subform.cleaned_data.get('warranty') or '').strip()
                    if use_avail:
                        item.availability = form_value
                        item.warranty = ''
                    else:
                        item.warranty = form_value
                        item.availability = ''
                    item.save()
                for obj in formset.deleted_objects:
                    obj.delete()
                # Save attachments
                attachments = attach_formset.save(commit=False)
                for att in attachments:
                    att.proposal = proposal
                    att.uploaded_by = request.user
                    att.save()
                for obj in attach_formset.deleted_objects:
                    obj.delete()
                
                proposal.calculate_totals()
                proposal.ensure_approval_chain()
                update_sales_funnel(proposal)

                # Notify the current pending approver only when the approval
                # workflow (re)started as a result of this edit — i.e. the chain
                # version changed. Avoids spamming on unrelated edits.
                proposal.refresh_from_db()
                if proposal.approval_required and proposal.approval_version != before_approval_version:
                    notify_pending_approver(proposal, request=request)

                # Change log
                changes = {}
                from django.forms.models import model_to_dict
                after = Proposal.objects.get(pk=proposal.pk)
                fields_to_check = ['customer_id','date','valid_until','stock_availability','subject','payment_terms','delivery_lead_time','warranty','special_note','introduction','closing','include_bank_details','show_discount','discount_amount','currency','exchange_rate']
                for f in fields_to_check:
                    if getattr(before, f) != getattr(after, f):
                        changes[f] = {'from': str(getattr(before, f)), 'to': str(getattr(after, f))}
                # Items
                after_use_avail = proposal.use_availability_column
                after_items = {
                    i.pk: {
                        'part_number': i.part_number,
                        'description': i.description,
                        'quantity': str(i.quantity),
                        'unit_cost': str(i.unit_cost),
                        'unit_price': str(i.unit_price),
                        'column_value': (i.availability if after_use_avail else i.warranty) or '',
                        'use_availability_column': after_use_avail,
                        'is_optional': i.is_optional,
                        'is_bundle': i.is_bundle,
                        'bundled_items': i.bundled_items,
                    }
                    for i in proposal.items.all()
                }
                item_changes = {}
                for pk_i, before_data in before_items.items():
                    if pk_i not in after_items:
                        item_changes[str(pk_i)] = {'status': 'deleted', 'before': before_data}
                    elif after_items[pk_i] != before_data:
                        item_changes[str(pk_i)] = {'status': 'updated', 'before': before_data, 'after': after_items[pk_i]}
                for pk_i, after_data in after_items.items():
                    if pk_i not in before_items:
                        item_changes[str(pk_i)] = {'status': 'added', 'after': after_data}
                if item_changes:
                    changes['items'] = item_changes
                if changes:
                    ProposalChangeLog.objects.create(proposal=proposal, changed_by=request.user, summary='Proposal updated', details=changes)
                
                messages.success(request, 'Proposal updated successfully.')
                return redirect('proposal_detail', pk=proposal.pk)
    else:
        form = ProposalForm(instance=proposal, user=request.user)
        formset = ProposalItemFormSet(instance=proposal)
        if proposal.use_availability_column:
            for item_form in formset:
                if item_form.instance and item_form.instance.availability:
                    item_form.initial = item_form.initial or {}
                    item_form.initial['warranty'] = item_form.instance.availability
        attach_formset = ProposalAttachmentFormSet(instance=proposal)
    
    return render(request, 'sales_proposals/proposal_form.html', {
        'form': form,
        'formset': formset,
        'attach_formset': attach_formset,
        'title': 'Edit Proposal',
        'proposal': proposal,
    })

@login_required
def proposal_detail(request, pk):
    proposal = get_object_or_404(Proposal, pk=pk)
    return render(request, 'sales_proposals/proposal_detail.html', {'proposal': proposal})

@login_required
def proposal_delete(request, pk):
    proposal = get_object_or_404(Proposal, pk=pk)
    if request.method == 'POST':
        proposal.delete()
        messages.success(request, 'Proposal deleted successfully.')
        return redirect('proposal_list')
    return render(request, 'sales_proposals/proposal_confirm_delete.html', {'proposal': proposal})

def generate_pdf_buffer(proposal):
    buffer = io.BytesIO()

    img_width = 7.5 * inch

    # --- Pre-calculate footer dimensions ---
    footer_img_path = os.path.join(settings.BASE_DIR, 'core/static/core/images/PROPOSAL-FOOTER.png')
    footer_height = 0
    footer_width = img_width

    if os.path.exists(footer_img_path):
        try:
            img_reader = ImageReader(footer_img_path)
            iw, ih = img_reader.getSize()
            aspect = ih / float(iw)
            footer_height = footer_width * aspect
        except:
            footer_height = 0.5 * inch

    # --- Pre-calculate header dimensions ---
    header_img_path = os.path.join(settings.BASE_DIR, 'core/static/core/images/Proposal_Header.png')
    header_height = 0
    header_has_image = False

    if os.path.exists(header_img_path):
        try:
            img_reader = ImageReader(header_img_path)
            iw, ih = img_reader.getSize()
            aspect = ih / float(iw)
            header_height = img_width * aspect
            header_has_image = True
        except:
            header_height = 1.2 * inch
            header_has_image = True

    # Margins: reserve space at top for header image + small gap; bottom for footer
    top_margin = (header_height + 14) if header_has_image else 36
    bottom_margin = max(36, footer_height + 20)

    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        rightMargin=36, leftMargin=36,
        topMargin=top_margin, bottomMargin=bottom_margin,
    )
    styles = getSampleStyleSheet()
    
    # Custom Colors
    MIC_RED = colors.HexColor('#B22222') # Firebrick red, approximating the screenshot
    MIC_YELLOW = colors.HexColor('#FFFFFF') # Yellow for the note
    
    # Custom Styles
    try:
        # Define potential font paths for different OS
        # Note: prioritized order. Liberation Sans is preferred on Linux as it supports the Peso sign (₱).
        # We check for Liberation Sans *before* Arial to avoid loading old Arial versions that lack the symbol.
        arial_paths = [
            # Bundled with project (PRIORITY — ensures same output on all platforms)
            os.path.join(settings.BASE_DIR, 'core/static/core/fonts/DejaVuSans.ttf'),
            os.path.join(settings.BASE_DIR, 'DejaVuSans.ttf'),
            # Ubuntu/Debian (System)
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
            # Bundled Liberation/Arial
            os.path.join(settings.BASE_DIR, 'core/static/core/fonts/LiberationSans-Regular.ttf'),
            os.path.join(settings.BASE_DIR, 'core/static/core/fonts/Arial.ttf'),
            # Arial - macOS
            '/System/Library/Fonts/Supplemental/Arial.ttf',
            '/usr/share/fonts/truetype/msttcorefonts/Arial.ttf',
            '/usr/share/fonts/truetype/msttcorefonts/arial.ttf',
            '/usr/share/fonts/TTF/Arial.ttf',
        ]
        
        arial_bold_paths = [
            # Bundled with project (PRIORITY — ensures same output on all platforms)
            os.path.join(settings.BASE_DIR, 'core/static/core/fonts/DejaVuSans-Bold.ttf'),
            os.path.join(settings.BASE_DIR, 'DejaVuSans-Bold.ttf'),
            # Ubuntu Systems
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
            # Bundled Liberation/Arial Bold
            os.path.join(settings.BASE_DIR, 'core/static/core/fonts/LiberationSans-Bold.ttf'),
            os.path.join(settings.BASE_DIR, 'core/static/core/fonts/Arial_Bold.ttf'),
            # Arial Bold - macOS
            '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
            '/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf',
            '/usr/share/fonts/truetype/msttcorefonts/arialbd.ttf',
            '/usr/share/fonts/TTF/Arialbd.ttf',
        ]
        
        # Find first existing Arial font
        arial_font = None
        for path in arial_paths:
            if os.path.exists(path):
                arial_font = path
                break
                
        # Find first existing Arial Bold font
        arial_bold_font = None
        for path in arial_bold_paths:
            if os.path.exists(path):
                arial_bold_font = path
                break
        
        if arial_font and arial_bold_font:
            pdfmetrics.registerFont(TTFont('Arial', arial_font))
            pdfmetrics.registerFont(TTFont('Arial-Bold', arial_bold_font))
            font_normal = 'Arial'
            font_bold = 'Arial-Bold'
        else:
            raise Exception("Arial font not found")
            
    except:
        # Fallback if Arial is not found anywhere
        font_normal = 'Helvetica'
        font_bold = 'Helvetica-Bold'

    styles.add(ParagraphStyle(name='HeaderContact', parent=styles['Normal'], fontName=font_normal, textColor=colors.white, fontSize=8, leading=10, alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='ProposalTitle', parent=styles['Heading1'], fontName=font_bold, fontSize=14, spaceAfter=6))
    styles.add(ParagraphStyle(name='NormalSmall', parent=styles['Normal'], fontName=font_normal, fontSize=9, leading=11))
    styles.add(ParagraphStyle(name='TableText', parent=styles['Normal'], fontName=font_normal, fontSize=8, leading=10))
    styles.add(ParagraphStyle(name='TableTextCenter', parent=styles['TableText'], alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='TableTextRight', parent=styles['TableText'], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='TableHeader', parent=styles['Normal'], fontName=font_bold, fontSize=8, leading=10, textColor=colors.white, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name='TableHeaderRight', parent=styles['TableHeader'], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name='NoteHeader', parent=styles['Normal'], fontName=font_bold, fontSize=9, backColor=MIC_YELLOW))

    # Cap how much of a line-item description renders in the PDF. Some items carry
    # a very long raw spec dump (e.g. 2,000+ chars of manufacturer config codes),
    # which produces a table cell taller than a whole page — ugly output and, before
    # splitInRow, a hard LayoutError. This trims the DISPLAY only (stored data is
    # untouched) so the row stays a sane height and the table renders cleanly.
    # NOTE: input-side validation is a separate, approved effort (see
    # docs/PROPOSAL_DESCRIPTION_LENGTH_PLAN.md); this is the render-side safety net.
    import html as _html_mod

    PDF_DESCRIPTION_MAX_CHARS = 600

    def _pdf_description(text):
        """Return HTML-safe description text for a PDF cell, trimmed if excessively long."""
        raw = (text or '').strip()
        if len(raw) <= PDF_DESCRIPTION_MAX_CHARS:
            return _html_mod.escape(raw).replace('\n', '<br/>')
        trimmed = raw[:PDF_DESCRIPTION_MAX_CHARS].rstrip()
        # Avoid cutting mid-word where possible.
        cut = trimmed.rfind(' ')
        if cut > PDF_DESCRIPTION_MAX_CHARS - 80:
            trimmed = trimmed[:cut]
        safe = _html_mod.escape(trimmed).replace('\n', '<br/>')
        return f"{safe} <font size='7'><i>… (specifications truncated)</i></font>"

    def draw_header_footer(canvas, doc):
        canvas.saveState()
        page_width = letter[0]

        # --- Draw header image (every page) ---
        if header_has_image:
            try:
                x_pos = (page_width - img_width) / 2
                # Position: top of page minus header height, with a small top margin
                y_pos = letter[1] - header_height - 6
                canvas.drawImage(
                    header_img_path, x_pos, y_pos,
                    width=img_width, height=header_height,
                    mask='auto',
                )
            except Exception:
                pass
        else:
            # Fallback text header drawn via canvas (no ReportLab Flowables available here)
            # Draw a simple red bar with company name
            bar_x = 36
            bar_y = letter[1] - 54
            canvas.setFillColor(colors.HexColor('#B22222'))
            canvas.rect(bar_x, bar_y, page_width - 72, 40, fill=1, stroke=0)
            canvas.setFillColor(colors.white)
            canvas.setFont('Helvetica-Bold', 10)
            canvas.drawString(bar_x + 6, bar_y + 14, 'MICRO IMAGE INTERNATIONAL CORPORATION')

        # --- Draw footer image (every page) ---
        if os.path.exists(footer_img_path):
            try:
                x_pos = (page_width - footer_width) / 2
                canvas.drawImage(
                    footer_img_path, x_pos, 10,
                    width=footer_width, height=footer_height,
                    mask='auto',
                )
            except Exception:
                pass

        canvas.restoreState()

    elements = []

    # Header is now drawn on every page via draw_header_footer callback.
    # Add a small spacer so content starts below the reserved top margin.
    elements.append(Spacer(1, 6))
    
    # --- REFERENCE INFO ---
    ref_no = proposal.reference_number if proposal.reference_number else proposal.proposal_number
    elements.append(Paragraph(f"Ref No: {ref_no}", styles['NormalSmall']))
    elements.append(Paragraph(f"{proposal.date.strftime('%B %d, %Y')}", styles['NormalSmall']))
    elements.append(Spacer(1, 12))
    
    # --- CUSTOMER INFO ---
    # Display in clean Title Case (contact person, company, address) without
    # altering the stored data. Values already in mixed case are left untouched.
    contact_name = _smart_title_case(proposal.contact_name or proposal.customer.contact_person_name)
    contact_email = proposal.contact_email or proposal.customer.email
    contact_phone = proposal.contact_phone or proposal.customer.phone_number
    company_name_display = _smart_title_case(proposal.customer.company_name)
    customer_address = _smart_title_case((proposal.customer.address or '').strip())
    elements.append(Paragraph(f"{contact_name}", styles['NormalSmall']))
    elements.append(Paragraph(f"<b>{company_name_display}</b>", styles['NormalSmall']))
    if customer_address:
        # Constrain the address to half the content width (7.5" usable -> 3.75")
        # so long single-line addresses wrap onto a second line instead of
        # spanning the full page width.
        addr_para = Paragraph(customer_address.replace('\n', '<br/>'), styles['NormalSmall'])
        addr_table = Table([[addr_para]], colWidths=[3.75 * inch])
        addr_table.hAlign = 'LEFT'
        addr_table.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(addr_table)
    if contact_phone:
        elements.append(Paragraph(contact_phone, styles['NormalSmall']))
    if contact_email:
        elements.append(Paragraph(f"<a href='mailto:{contact_email}'>{contact_email}</a>", styles['NormalSmall']))
    elements.append(Spacer(1, 12))
    
    # --- SALUTATION ---
    salutation_name = (contact_name or "").strip()
    elements.append(Paragraph(f"Dear {salutation_name if salutation_name else 'Sir/Madame'},", styles['NormalSmall']))
    elements.append(Spacer(1, 6))
    
    # --- OPENING ---
    intro_text = proposal.introduction if proposal.introduction else \
        "Micro Image International Corporation, an experienced and reputable IT products & services provider, with partnership appointments from various industry-leading products, is pleased to submit its quotation for your IT requirements."
    elements.append(Paragraph(intro_text, styles['NormalSmall']))
    elements.append(Spacer(1, 12))
    
    # --- ITEMS TABLE ---
    currency_symbol = '₱' if proposal.currency == 'PHP' else '$'
    price_col_header = "TOTAL PRICE"
    # Availability/Warranty column toggle — per-proposal setting
    avail_col_header = "AVAILABILITY" if proposal.use_availability_column else "WARRANTY"

    def _avail_cell(item):
        """Return the availability or warranty value for a line item."""
        if proposal.use_availability_column:
            return item.availability or ''
        return item.warranty or proposal.warranty or ''

    # --- Column layout (per-proposal "Hide Part No." toggle) ---
    # The natural 7 columns are: ITEM, PART NO., DESCRIPTION, QTY, UNIT PRICE,
    # (TOTAL) PRICE, AVAILABILITY/WARRANTY. When hide_part_number is set we drop
    # the PART NO. column (index 1) from every row and hand its width to
    # DESCRIPTION. To keep the index-based TableStyle coordinates correct in both
    # cases, we compute them symbolically here.
    hide_pn = bool(getattr(proposal, 'hide_part_number', False))

    def _row(cells):
        """Given the full 7-cell row (with the Part No. cell at index 1), return
        the row with that cell removed when the Part No. column is hidden."""
        return [c for i, c in enumerate(cells) if not (hide_pn and i == 1)]

    # Symbolic column indices AFTER any drop (used by TableStyle coordinates).
    # Full:   0=ITEM 1=PART 2=DESC 3=QTY 4=UNIT 5=PRICE 6=AVAIL
    # Hidden: 0=ITEM        1=DESC 2=QTY 3=UNIT 4=PRICE 5=AVAIL
    COL_DESC = 1 if hide_pn else 2          # description column (left-aligned)
    COL_PRICE_LABEL = 3 if hide_pn else 4   # "Subtotal/Total Investment" label cell
    COL_PRICE_VALUE = 4 if hide_pn else 5   # the amount cell
    COL_LAST = 5 if hide_pn else 6          # last column index (availability)

    # Column widths — Part No.'s 1.1" is added to Description when hidden.
    if hide_pn:
        col_widths = [0.55*inch, (1.9 + 1.1)*inch, 0.5*inch, 1.05*inch, 1.3*inch, 1.1*inch]
    else:
        col_widths = [0.55*inch, 1.1*inch, 1.9*inch, 0.5*inch, 1.05*inch, 1.3*inch, 1.1*inch]

    if proposal.is_multi_option:
        # ===============================================================
        # MULTI-OPTION FORMAT: Separate table per option group
        # ===============================================================
        # Style for the "OPTION N" heading, rendered as a spanning first row
        # INSIDE each option table (see below). Making the heading part of the
        # table means the heading + column header + data rows are a single
        # splittable flowable: it fills the current page and only breaks when
        # the page is actually full — so the heading can never be orphaned AND
        # there is no large blank gap from pushing a whole block to a new page.
        option_title_style = ParagraphStyle(
            name='OptionTitleCell', parent=styles['NormalSmall'],
            fontName=font_bold, fontSize=11, textColor=MIC_RED,
            spaceBefore=0, spaceAfter=0, leading=14,
        )

        for group in proposal.option_groups.all():
            # Row 0: full-width "OPTION N" heading cell (spanned across all cols)
            group_table_data = [_row([
                Paragraph(group.name.upper(), option_title_style),
                '', '', '', '', '', '',
            ])]

            # Row 1: column header
            group_table_data.append(_row([
                Paragraph("ITEM", styles['TableHeader']),
                Paragraph("PART NO.", styles['TableHeader']),
                Paragraph("DESCRIPTION", styles['TableHeader']),
                Paragraph("QTY", styles['TableHeader']),
                Paragraph("UNIT PRICE", styles['TableHeader']),
                Paragraph(price_col_header, styles['TableHeader']),
                Paragraph(avail_col_header, styles['TableHeader']),
            ]))

            for idx, item in enumerate(group.group_items.all(), start=1):
                group_table_data.append(_row([
                    Paragraph(str(idx), styles['TableTextCenter']),
                    Paragraph(item.part_number or '', styles['TableText']),
                    Paragraph(_pdf_description(item.description), styles['TableText']),
                    Paragraph(str(int(item.quantity)) if item.quantity % 1 == 0 else str(item.quantity), styles['TableTextCenter']),
                    Paragraph(f"{currency_symbol}{item.unit_price:,.2f}", styles['TableTextRight']),
                    Paragraph(f"{currency_symbol}{item.amount:,.2f}", styles['TableTextRight']),
                    Paragraph(_avail_cell(item), styles['TableTextCenter']),
                ]))
                for component in item.bundle_components:
                    group_table_data.append(_row([
                        '', 
                        Paragraph(component['part_number'] or '', styles['TableText']),
                        Paragraph(_pdf_description(component['description']), styles['TableText']),
                        Paragraph(
                            str(int(component['quantity'])) if component.get('quantity') is not None and component['quantity'] % 1 == 0
                            else (str(component['quantity']) if component.get('quantity') is not None else ''),
                            styles['TableTextCenter'],
                        ),
                        '', '', '',
                    ]))

            # Total Investment row for this option
            group_table_data.append(_row([
                '', '', '', '',
                Paragraph("Total Investment", styles['TableHeader']),
                Paragraph(f"{currency_symbol}{group.subtotal:,.2f}", styles['TableHeaderRight']),
                '',
            ]))

            # repeatRows=2 repeats the OPTION heading (row 0) + column header
            # (row 1) at the top of each continuation page if the table splits.
            # Rows break WHOLE across pages (no splitInRow): a data row that doesn't
            # fit moves entirely to the next page, avoiding an orphaned header stripe
            # + partial row at the bottom. Descriptions are length-capped by
            # _pdf_description, so no single row can exceed a page (which is what
            # previously forced splitInRow / caused the LayoutError).
            gt = Table(group_table_data, colWidths=col_widths, repeatRows=2)
            # Anchor the table to the left margin so it lines up with the body text.
            gt.hAlign = 'LEFT'
            gt_style = [
                # Row 0: "OPTION N" heading — spans all columns, no fill, red
                # text, left-aligned, and NO grid lines (matches prior look).
                ('SPAN', (0, 0), (-1, 0)),
                ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
                ('LEFTPADDING', (0, 0), (0, 0), 0),
                ('TOPPADDING', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
                # Row 1: column header (red background, white text).
                ('BACKGROUND', (0, 1), (-1, 1), MIC_RED),
                ('TEXTCOLOR', (0, 1), (-1, 1), colors.white),
                ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
                # Grid on the column header + data rows only (skip heading row 0
                # and the Total Investment row -2..-1 handled below).
                ('GRID', (0, 1), (-1, -2), 1, colors.black),
                ('ALIGN', (COL_DESC, 2), (COL_DESC, -2), 'LEFT'),
                # Total Investment row styling (red background, white text)
                ('BACKGROUND', (COL_PRICE_LABEL, -1), (COL_PRICE_VALUE, -1), MIC_RED),
                ('TEXTCOLOR', (COL_PRICE_LABEL, -1), (COL_PRICE_VALUE, -1), colors.white),
                ('GRID', (COL_PRICE_LABEL, -1), (COL_PRICE_VALUE, -1), 1, MIC_RED),
            ]
            gt.setStyle(TableStyle(gt_style))

            # Single splittable table per option. Because the heading is row 0
            # of the table, ReportLab keeps it with the following rows and fills
            # the current page, breaking only when the page is full. No
            # KeepTogether/keepWithNext, so no large blank gap on the prior page.
            elements.append(gt)
            elements.append(Spacer(1, 14))

    else:
        # ===============================================================
        # STANDARD SINGLE FORMAT (existing logic — unchanged)
        # ===============================================================
        table_data = [_row([
            Paragraph("ITEM", styles['TableHeader']),
            Paragraph("PART NO.", styles['TableHeader']),
            Paragraph("DESCRIPTION", styles['TableHeader']),
            Paragraph("QTY", styles['TableHeader']),
            Paragraph("UNIT PRICE", styles['TableHeader']),
            Paragraph(price_col_header, styles['TableHeader']),
            Paragraph(avail_col_header, styles['TableHeader'])
        ])]
    
        for idx, item in enumerate(proposal.items.all(), start=1):
            table_data.append(_row([
                Paragraph(str(idx), styles['TableTextCenter']),
                Paragraph(item.part_number or '', styles['TableText']),
                Paragraph(
                    (
                        f"{_pdf_description(item.description)}<br/><font size='7'><i>Option {item.optional_option_number}</i></font>"
                        if item.is_optional and item.description
                        else (f"<font size='7'><i>Option {item.optional_option_number}</i></font>" if item.is_optional else _pdf_description(item.description))
                    ),
                    styles['TableText'],
                ),
                Paragraph(str(int(item.quantity)) if item.quantity % 1 == 0 else str(item.quantity), styles['TableTextCenter']),
                Paragraph(f"{currency_symbol}{item.unit_price:,.2f}", styles['TableTextRight']),
                Paragraph(f"{currency_symbol}{item.amount:,.2f}", styles['TableTextRight']),
                Paragraph(_avail_cell(item), styles['TableTextCenter'])
            ]))
            for component in item.bundle_components:
                table_data.append(_row([
                    '',
                    Paragraph(component['part_number'] or '', styles['TableText']),
                    Paragraph(_pdf_description(component['description']), styles['TableText']),
                    Paragraph(
                        (
                            str(int(component['quantity'])) if component.get('quantity') is not None and component['quantity'] % 1 == 0
                            else (str(component['quantity']) if component.get('quantity') is not None else '')
                        ),
                        styles['TableTextCenter'],
                    ),
                    '',
                    '',
                    '',
                ]))
    
        if not proposal.has_optional_items:
            # Subtotal
            table_data.append(_row([
                '', '', '', '', 
                Paragraph("Subtotal", styles['TableText']), 
                Paragraph(f"{currency_symbol}{proposal.subtotal:,.2f}", styles['TableTextRight']), 
                ''
            ]))

            if proposal.show_discount and (proposal.discount_amount or 0) > 0:
                table_data.append(_row([
                    '', '', '', '',
                    Paragraph("Discount", styles['TableText']),
                    Paragraph(f"-{currency_symbol}{proposal.discount_amount:,.2f}", styles['TableTextRight']),
                    ''
                ]))

            if proposal.show_vat:
                table_data.append(_row([
                    '', '', '', '',
                    Paragraph("VAT (12%)", styles['TableText']),
                    Paragraph(f"{currency_symbol}{proposal.tax_amount:,.2f}", styles['TableTextRight']),
                    ''
                ]))

            grand_total_label = "Grand Total (VAT incl.)" if proposal.show_vat else "Grand Total"
            # Grand Total Row
            table_data.append(_row([
                '', '', '', '', 
                Paragraph(grand_total_label, styles['TableHeader']), 
                Paragraph(f"{currency_symbol}{proposal.total_amount:,.2f}", styles['TableHeaderRight']), 
                ''
            ]))
    
        # col_widths was computed above (Part No.'s width folds into Description
        # when hide_part_number is set).
        # Rows break WHOLE across pages (no splitInRow): a data row that doesn't fit
        # moves entirely to the next page, avoiding an orphaned header stripe +
        # partial row at the bottom of a page. Descriptions are length-capped by
        # _pdf_description, so no single row can exceed a page (which is what
        # previously forced splitInRow / caused the LayoutError).
        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        # Anchor the table to the left margin so it lines up with the body text
        # (default is CENTER, which pushes the left edge past the text margin).
        t.hAlign = 'LEFT'
    
        # Styling
        table_grid_end_row = -2 if not proposal.has_optional_items else -1
        table_align_end_row = -2 if not proposal.has_optional_items else -1
        table_style = [
            ('BACKGROUND', (0,0), (-1,0), MIC_RED), # Header Background
            ('TEXTCOLOR', (0,0), (-1,0), colors.white), # Header Text
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('GRID', (0,0), (-1,table_grid_end_row), 1, colors.black),
            ('ALIGN', (COL_DESC,1), (COL_DESC,table_align_end_row), 'LEFT'),
        ]
        if not proposal.has_optional_items:
            table_style.extend([
                ('BACKGROUND', (COL_PRICE_LABEL,-1), (COL_LAST,-1), MIC_RED),
                ('TEXTCOLOR', (COL_PRICE_LABEL,-1), (COL_LAST,-1), colors.white),
                ('GRID', (COL_PRICE_LABEL,-1), (COL_LAST,-1), 1, MIC_RED),
            ])
        t.setStyle(TableStyle(table_style))
        elements.append(t)
        elements.append(Spacer(1, 12))
    
    # --- NOTE ---
    if proposal.special_note:
        elements.append(Paragraph("Special Note:", styles['NormalSmall']))
        elements.append(Paragraph(proposal.special_note, styles['NoteHeader']))
        elements.append(Spacer(1, 12))
    
    # --- TERMS AND CONDITIONS ---
    tc_style = ParagraphStyle(name='TCText', parent=styles['NormalSmall'])
    tc_label = ParagraphStyle(name='TCLabel', parent=styles['NormalSmall'], fontName=font_bold)
    
    # Cancellation Text — always uses the short & polite wording
    cancellation_text = "Please be advised that once a Purchase Order is confirmed, it is firm and cannot be cancelled without liability. Should a cancellation occur, the client agrees to a fee amounting to 100% of the PO value."
    
    validity_text = f"Valid until {proposal.valid_until.strftime('%B %d, %Y') if proposal.valid_until else 'N/A'} only."
    
    tc_data = [
        [Paragraph("Terms and Conditions:", tc_label), ''],
        [Paragraph("Price Validity", tc_label), Paragraph(validity_text, tc_style)],
        [Paragraph("Stock Availability", tc_label), Paragraph(proposal.stock_availability or "N/A", tc_style)],
        [Paragraph("Payment Terms", tc_label), Paragraph((proposal.payment_terms or '').replace('\n', '<br/>'), tc_style)],
        [Paragraph("Cancellation", tc_label), Paragraph(cancellation_text, tc_style)],
    ]

    BANK_NOTIFICATION_EMAIL = "abengo@microimageph.com / jtorrefranca@microimageph.com"

    if proposal.include_bank_details:
        if proposal.currency == 'USD':
            bank_html = (
                f"<b>USD — {proposal.usd_bank_name}</b><br/>"
                f"Beneficiary: {proposal.usd_beneficiary_name}<br/>"
                f"Beneficiary Address: {proposal.usd_beneficiary_address}<br/>"
                f"Account Number: {proposal.usd_account_number}<br/>"
                f"Bank Address: {proposal.usd_bank_address}<br/>"
                f"Swift Code (BIC): {proposal.usd_swift_code}<br/>"
                f"Branch Code: {proposal.usd_branch_code}<br/>"
                f"Payment Notification Email: {BANK_NOTIFICATION_EMAIL}"
            )
        else:
            bdo_html = (
                f"<b>BDO — Banco De Oro</b><br/>"
                f"Account Name: {proposal.php_account_name}<br/>"
                f"Account Number: {proposal.php_account_number} ({proposal.php_account_type})<br/>"
                f"Branch: {proposal.php_branch}<br/>"
                f"Bank Address: {proposal.php_bank_address}<br/>"
                f"Swift Code: {proposal.php_swift_code} &nbsp; Branch Code: {proposal.php_branch_code}"
            )
            bpi_html = (
                f"<b>BPI — Bank of the Philippine Islands</b><br/>"
                f"Account Name: {proposal.php_bpi_account_name}<br/>"
                f"Account Number: {proposal.php_bpi_account_number} ({proposal.php_bpi_account_type})<br/>"
                f"Branch: {proposal.php_bpi_branch}<br/>"
                f"Bank Address: {proposal.php_bpi_bank_address}<br/>"
                f"Swift Code: {proposal.php_bpi_swift_code}"
            )
            bank_html = (
                bdo_html + "<br/><br/>" + bpi_html
                + f"<br/><br/><i>Payment Notification Email: {BANK_NOTIFICATION_EMAIL}</i>"
            )
        tc_data.append([Paragraph("Bank Details", tc_label), Paragraph(bank_html, tc_style)])

    tc_data.extend([
        [Paragraph("Delivery Lead time", tc_label), Paragraph(proposal.delivery_lead_time, tc_style)],
    ])
    
    if proposal.closing:
         tc_data.append([Paragraph("Other Terms", tc_label), Paragraph(proposal.closing.replace('\n', '<br/>'), tc_style)])

    tc_table = Table(tc_data, colWidths=[1.8*inch, 5.7*inch])
    tc_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (0,0), (0,-1), 'LEFT'),
        # Make the section header span both columns to avoid wrapping
        ('SPAN', (0,0), (1,0)),
        ('BOTTOMPADDING', (0,0), (1,0), 6),
    ]))
    elements.append(tc_table)
    elements.append(Spacer(1, 12))
    
    # --- CLOSING & SIGNATURES ---
    # We group Closing text + Signatures into a KeepTogether block to ensure they stay on the same page
    # If they don't fit, they will move to the next page together.
    
    closing_elements = []
    
    closing_elements.append(Paragraph("We trust that you keep this proposal with confidentiality and we hope that you find everything in order.", styles['NormalSmall']))
    closing_elements.append(Paragraph("Please fax Purchase Order/approval/conforme at (632) 894-25-90.", styles['NormalSmall']))
    closing_elements.append(Paragraph("Should you have any additional concern, please feel free to contact us.", styles['NormalSmall']))
    closing_elements.append(Spacer(1, 18))
    closing_elements.append(Paragraph("Very truly yours,", styles['NormalSmall']))
    closing_elements.append(Spacer(1, 4))
    
    signature_img = None
    try:
        if hasattr(proposal.created_by, 'signature_image') and proposal.created_by.signature_image and proposal.created_by.signature_image.path:
            # Slightly smaller height and let the image sit closer to the line
            signature_img = Image(proposal.created_by.signature_image.path, width=2*inch, height=0.5*inch)
    except Exception:
        signature_img = None
    
    # Determine job title dynamically (same logic as email signature)
    sig_job_title = ''
    if getattr(proposal.created_by, 'job_title', ''):
        sig_job_title = proposal.created_by.get_job_title_display()
    elif getattr(proposal.created_by, 'role', ''):
        sig_job_title = proposal.created_by.get_role_display()
    sig_job_title = sig_job_title or 'Corporate Account Manager'

    sig_data = [
        ['', 'Conforme:'],
        [signature_img or '', ''],
        ['__________________________', '__________________________'],
        [Paragraph(f"<b>{proposal.created_by.get_full_name()}</b><br/>{sig_job_title}<br/>Mobile #: {proposal.created_by.mobile_number or ''}", styles['NormalSmall']), 
         Paragraph("Print Name & Sign<br/>Served as Order if signed by Authorized <br/>Representative", styles['NormalSmall'])]
    ]
    sig_table = Table(sig_data, colWidths=[3.5*inch, 4*inch])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        # Tighten the whole block so it reads as one compact signature area.
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        # Row 0 (Conforme header) — small breathing space only under the header text
        ('BOTTOMPADDING', (0,0), (-1,0), 2),
        # Row 1 (signature image) sits right on the line below it
        ('VALIGN', (0,1), (0,1), 'BOTTOM'),
        ('BOTTOMPADDING', (0,1), (-1,1), 0),
        # Row 3 (name/title block) gets a little space under the line
        ('TOPPADDING', (0,3), (-1,3), 2),
    ]))
    closing_elements.append(sig_table)
    
    elements.append(KeepTogether(closing_elements))
    
    # --- FOOTER ---
    # Implemented via onFirstPage/onLaterPages callbacks
    
    doc.build(elements, onFirstPage=draw_header_footer, onLaterPages=draw_header_footer)
    buffer.seek(0)
    return buffer

@login_required
def proposal_pdf(request, pk):
    proposal = get_object_or_404(Proposal, pk=pk)
    buffer = generate_pdf_buffer(proposal)
    return HttpResponse(buffer, content_type='application/pdf')

@login_required
def proposal_email(request, pk):
    proposal = get_object_or_404(Proposal, pk=pk)
    # Block sending an empty proposal (no line items => ₱0.00 quotation)
    if not proposal.has_line_items:
        messages.warning(request, "This proposal has no items. Add at least one item before emailing the customer.")
        return redirect('proposal_detail', pk=pk)
    if proposal.approval_required and proposal.approval_status != 'approved':
        messages.warning(request, f"Approval required before sending. Current status: {proposal.get_approval_status_display()}")
        return redirect('proposal_detail', pk=pk)
    
    # Determine supervisor email
    supervisor_email = None
    try:
        if hasattr(request.user, 'team_membership'):
            group = request.user.team_membership.group
            manager = group.get_manager()
            if manager and manager.email:
                supervisor_email = manager.email
    except Exception:
        pass
    
    # Build CC contacts list (main + additional with emails)
    try:
        from customers.models import CustomerContact
        additional_contacts = list(CustomerContact.objects.filter(customer=proposal.customer).order_by('-is_primary','name'))
    except Exception:
        additional_contacts = []
    cc_contacts = []
    # Main contact option
    if proposal.customer.email:
        cc_contacts.append({
            'label': f"{proposal.customer.contact_person_name or 'Main Contact'}",
            'email': proposal.customer.email
        })
    # Additional contact options
    for c in additional_contacts:
        if c.email:
            cc_contacts.append({
                'label': c.name,
                'email': c.email
            })
    
    if request.method == 'POST':
        # Get recipient emails (comma/semicolon separated supported)
        raw_to = request.POST.get('customer_emails') or request.POST.get('customer_email') or (proposal.contact_email or proposal.customer.email)
        to_list = []
        if raw_to:
            import re
            to_list = [e.strip() for e in re.split(r'[,\s;]+', raw_to) if e.strip()]
        # Fallback to single default if parsing produced none
        if not to_list and (proposal.contact_email or proposal.customer.email):
            to_list = [proposal.contact_email or proposal.customer.email]
        
        # Check for CC Supervisor
        cc_list = []
        if request.POST.get('cc_supervisor') == 'on' and supervisor_email:
            cc_list.append(supervisor_email)
        
        # Selected CC contacts
        for email in request.POST.getlist('cc_contact'):
            if email:
                cc_list.append(email.strip())
        
        # Free-form CCs (comma/semicolon separated)
        extra_cc = (request.POST.get('cc_emails') or '').strip()
        if extra_cc:
            import re
            pieces = re.split(r'[,\s;]+', extra_cc)
            for e in pieces:
                e = e.strip()
                if e:
                    cc_list.append(e)
        
        # Deduplicate and avoid duplicating To:
        lower_to = set([e.lower() for e in to_list])
        dedup_cc = []
        for i, e in enumerate(cc_list):
            if not e:
                continue
            el = e.lower()
            if el in lower_to:
                continue
            if e not in dedup_cc:
                dedup_cc.append(e)
        cc_list = dedup_cc
            
        # Generate PDF
        buffer = generate_pdf_buffer(proposal)
        
        # Attachments selected
        attach_ids = request.POST.getlist('attach_id')
        selected_attachments = [
            att
            for att in proposal.attachments.filter(id__in=attach_ids)
            if att.can_include_in_email
        ]

        # Send Email
        subject = f"Proposal: {proposal.subject} - {proposal.proposal_number}"
        cover = (request.POST.get('cover_message') or '').strip()
        if not cover:
            cover = f"""Dear {proposal.contact_name or proposal.customer.contact_person_name},

Please find attached our proposal for {proposal.subject}.

Best regards,"""
        signature_context = _get_proposal_email_signature_context(request.user)
        html_message = render_to_string(
            'sales_proposals/email/proposal_email_body.html',
            {
                'cover_message': cover,
                'proposal': proposal,
                'signature': signature_context,
            },
        )
        text_message = _build_proposal_email_text(cover, signature_context)
        from_email = request.user.email or settings.DEFAULT_FROM_EMAIL
        email = EmailMultiAlternatives(
            subject,
            text_message,
            from_email,
            to_list,
            cc=cc_list,
            reply_to=[request.user.email]
        )
        email.attach_alternative(html_message, 'text/html')
        for asset in signature_context['inline_images']:
            _attach_inline_image(email, asset['cid'], asset['path'])
        email.attach(f"{proposal.proposal_number}.pdf", buffer.getvalue(), 'application/pdf')
        for att in selected_attachments:
            if att.file:
                email.attach(att.file.name.split('/')[-1], att.file.read(), 'application/octet-stream')
        
        try:
            email.send()
            proposal.status = 'sent'
            proposal.save()
            
            # Log successful send
            ProposalEmailLog.objects.create(
                proposal=proposal,
                sent_by=request.user,
                recipients=', '.join(to_list),
                cc=', '.join(cc_list),
                status='sent',
            )
            
            # Log Activity
            log_sales_activity(proposal, request.user)
            
            # Update Funnel
            update_sales_funnel(proposal)
            
            recipients_str = ', '.join(to_list)
            msg = f"Proposal sent to {recipients_str}"
            if cc_list:
                msg += f" (CC: {', '.join(cc_list)})"
            messages.success(request, msg)
        except smtplib.SMTPRecipientsRefused as e:
            bad_addrs = ', '.join(e.recipients.keys())
            error_detail = f"Recipient(s) refused by mail server: {bad_addrs}"
            ProposalEmailLog.objects.create(
                proposal=proposal,
                sent_by=request.user,
                recipients=', '.join(to_list),
                cc=', '.join(cc_list),
                status='failed',
                error_message=error_detail,
            )
            messages.error(request, f"Failed to send — invalid recipient(s): {bad_addrs}")
        except smtplib.SMTPServerDisconnected:
            error_detail = "SMTP server disconnected unexpectedly"
            ProposalEmailLog.objects.create(
                proposal=proposal,
                sent_by=request.user,
                recipients=', '.join(to_list),
                cc=', '.join(cc_list),
                status='failed',
                error_message=error_detail,
            )
            messages.error(request, "Email server connection lost. Please try again.")
        except (socket.timeout, TimeoutError) as e:
            error_detail = f"Connection timed out: {str(e)}"
            ProposalEmailLog.objects.create(
                proposal=proposal,
                sent_by=request.user,
                recipients=', '.join(to_list),
                cc=', '.join(cc_list),
                status='failed',
                error_message=error_detail,
            )
            messages.error(request, "Email server timed out. Please try again later.")
        except Exception as e:
            error_detail = str(e)
            ProposalEmailLog.objects.create(
                proposal=proposal,
                sent_by=request.user,
                recipients=', '.join(to_list),
                cc=', '.join(cc_list),
                status='failed',
                error_message=error_detail,
            )
            messages.error(request, f"Failed to send email: {error_detail}")
            
        return redirect('proposal_detail', pk=pk)
    
    return render(request, 'sales_proposals/proposal_email_confirm.html', {
        'proposal': proposal,
        'supervisor_email': supervisor_email,
        'cc_contacts': cc_contacts
    })

@login_required
def approvals_inbox(request):
    steps = (
        ProposalApprovalStep.objects
        .filter(approver=request.user, status='pending')
        .annotate(
            current_pending_level=Min(
                'proposal__approval_steps__level',
                filter=Q(proposal__approval_steps__status='pending')
            )
        )
        .filter(level=F('current_pending_level'))
        .select_related('proposal', 'proposal__customer')
        .order_by('-proposal__approval_submitted_at', '-created_at')
    )
    return render(request, 'sales_proposals/approvals_inbox.html', {'steps': steps})

@login_required
def approve_proposal(request, pk):
    proposal = get_object_or_404(Proposal, pk=pk)
    if proposal.approval_status == 'rejected':
        messages.error(request, 'This proposal was already rejected and cannot be approved.')
        return redirect('proposal_detail', pk=pk)
    current_step = proposal.get_current_pending_step()
    step = ProposalApprovalStep.objects.filter(
        proposal=proposal,
        approver=request.user,
        status='pending'
    ).order_by('level').first()
    if not step:
        messages.error(request, 'No pending approval step assigned to you.')
        return redirect('proposal_detail', pk=pk)
    if not current_step or current_step.id != step.id:
        waiting_label = f'Level {current_step.level}' if current_step else 'the current approval level'
        waiting_name = current_step.approver.get_full_name() or current_step.approver.username if current_step and current_step.approver else 'the assigned approver'
        messages.error(request, f'Approval order is enforced. Please wait for {waiting_label} ({waiting_name}) first.')
        return redirect('proposal_detail', pk=pk)
    if request.method == 'POST':
        step.status = 'approved'
        step.decided_at = timezone.now()
        step.comment = request.POST.get('comment', '')
        step.save()
        next_step = ProposalApprovalStep.objects.filter(proposal=proposal, status='pending').order_by('level').first()
        if not next_step:
            proposal.approval_status = 'approved'
            proposal.approved_at = timezone.now()
            proposal.save()
            # Notify the salesperson their proposal is fully approved.
            notify_creator_of_decision(
                proposal, 'approved', decided_by=request.user,
                comment=step.comment, request=request,
            )
            messages.success(request, 'Proposal fully approved.')
        else:
            # Notify the next approver in the chain that it's now their turn.
            notify_pending_approver(proposal, request=request)
            messages.success(request, 'Step approved. Awaiting next approver.')
        return redirect('proposal_detail', pk=pk)
    return render(request, 'sales_proposals/approve_confirm.html', {'proposal': proposal})

@login_required
def reject_proposal(request, pk):
    proposal = get_object_or_404(Proposal, pk=pk)
    current_step = proposal.get_current_pending_step()
    step = ProposalApprovalStep.objects.filter(
        proposal=proposal,
        approver=request.user,
        status='pending'
    ).order_by('level').first()
    if not step:
        messages.error(request, 'No pending approval step assigned to you.')
        return redirect('proposal_detail', pk=pk)
    if not current_step or current_step.id != step.id:
        waiting_label = f'Level {current_step.level}' if current_step else 'the current approval level'
        waiting_name = current_step.approver.get_full_name() or current_step.approver.username if current_step and current_step.approver else 'the assigned approver'
        messages.error(request, f'Approval order is enforced. Please wait for {waiting_label} ({waiting_name}) first.')
        return redirect('proposal_detail', pk=pk)
    if request.method == 'POST':
        step.status = 'rejected'
        step.decided_at = timezone.now()
        step.comment = request.POST.get('comment', '')
        step.save()
        proposal.approval_status = 'rejected'
        proposal.save()
        # Close the rest of the chain so a later approver cannot act on — and
        # thereby un-reject — this proposal.
        ProposalApprovalStep.objects.filter(
            proposal=proposal, status='pending'
        ).update(status='cancelled', decided_at=timezone.now())
        # Notify the salesperson their proposal was rejected (with the reason).
        notify_creator_of_decision(
            proposal, 'rejected', decided_by=request.user,
            comment=step.comment, request=request,
        )
        messages.warning(request, 'Proposal rejected.')
        return redirect('proposal_detail', pk=pk)
    return render(request, 'sales_proposals/reject_confirm.html', {'proposal': proposal})

def _is_exec(user):
    return user.role in ['admin', 'president', 'vp', 'avp', 'gm']

@login_required
def approval_tier_list(request):
    if not _is_exec(request.user):
        messages.error(request, 'Not authorized')
        return redirect('proposal_list')
    tiers = ProposalApprovalTier.objects.all()
    return render(request, 'sales_proposals/approval_tier_list.html', {'tiers': tiers})

@login_required
def approval_tier_create(request):
    if not _is_exec(request.user):
        messages.error(request, 'Not authorized')
        return redirect('proposal_list')
    if request.method == 'POST':
        form = ProposalApprovalTierForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Approval tier created')
            return redirect('approval_tier_list')
    else:
        # Pre-check Active so new tiers are live by default
        form = ProposalApprovalTierForm(initial={'active': True})
    return render(request, 'sales_proposals/approval_tier_form.html', {'form': form, 'title': 'Create Approval Tier'})

@login_required
def approval_tier_edit(request, pk):
    if not _is_exec(request.user):
        messages.error(request, 'Not authorized')
        return redirect('proposal_list')
    tier = get_object_or_404(ProposalApprovalTier, pk=pk)
    if request.method == 'POST':
        form = ProposalApprovalTierForm(request.POST, instance=tier)
        if form.is_valid():
            form.save()
            messages.success(request, 'Approval tier updated')
            return redirect('approval_tier_list')
    else:
        form = ProposalApprovalTierForm(instance=tier)
    return render(request, 'sales_proposals/approval_tier_form.html', {'form': form, 'title': 'Edit Approval Tier'})

@login_required
def approval_tier_delete(request, pk):
    if not _is_exec(request.user):
        messages.error(request, 'Not authorized')
        return redirect('proposal_list')
    tier = get_object_or_404(ProposalApprovalTier, pk=pk)
    if request.method == 'POST':
        tier.delete()
        messages.success(request, 'Approval tier deleted')
        return redirect('approval_tier_list')
    return render(request, 'sales_proposals/approval_tier_confirm_delete.html', {'tier': tier})

@login_required
def approval_tier_export(request):
    if not _is_exec(request.user):
        messages.error(request, 'Not authorized')
        return redirect('proposal_list')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="approval_tiers_export.csv"'
    writer = csv.writer(response)
    writer.writerow(['name', 'min_amount_php', 'max_amount_php', 'chain', 'order', 'active'])
    for t in ProposalApprovalTier.objects.all().order_by('order', 'min_amount_php'):
        writer.writerow([t.name or '', str(t.min_amount_php), '' if t.max_amount_php is None else str(t.max_amount_php), t.chain, t.order, 'true' if t.active else 'false'])
    return response

@login_required
def approval_tier_template(request):
    if not _is_exec(request.user):
        messages.error(request, 'Not authorized')
        return redirect('proposal_list')
    template_path = os.path.join(settings.BASE_DIR, 'sales_proposals', 'sample_templates', 'approval_tiers_template.csv')
    return FileResponse(open(template_path, 'rb'), as_attachment=True, filename='approval_tiers_template.csv')

@login_required
def approval_tier_import(request):
    if not _is_exec(request.user):
        messages.error(request, 'Not authorized')
        return redirect('proposal_list')
    if request.method == 'POST':
        form = ProposalApprovalTierImportForm(request.POST, request.FILES)
        if form.is_valid():
            f = form.cleaned_data['file']
            replace = form.cleaned_data['replace_existing']
            decoded = f.read().decode('utf-8').splitlines()
            reader = csv.DictReader(decoded)
            rows = list(reader)
            if replace:
                ProposalApprovalTier.objects.all().delete()
            created = 0
            for r in rows:
                name = (r.get('name') or '').strip()
                min_amt = Decimal((r.get('min_amount_php') or '0').strip() or '0')
                max_raw = (r.get('max_amount_php') or '').strip()
                max_amt = Decimal(max_raw) if max_raw not in ['', None] else None
                chain = (r.get('chain') or '').strip()
                order = int((r.get('order') or '0').strip() or '0')
                active_val = (r.get('active') or '').strip().lower()
                active = active_val in ['1', 'true', 'yes', 'y']
                ProposalApprovalTier.objects.create(name=name, min_amount_php=min_amt, max_amount_php=max_amt, chain=chain, order=order, active=active)
                created += 1
            messages.success(request, f'Imported {created} tiers')
            return redirect('approval_tier_list')
    else:
        form = ProposalApprovalTierImportForm()
    return render(request, 'sales_proposals/approval_tier_import.html', {'form': form})

@login_required
def approval_tier_seed_defaults(request):
    if not _is_exec(request.user):
        messages.error(request, 'Not authorized')
        return redirect('proposal_list')
    if request.method != 'POST':
        return redirect('approval_tier_list')
    seeds = [
        dict(name='Supervisor Tier', min=Decimal('500000'), max=Decimal('999999'), chain='supervisor', order=1, active=True),
        dict(name='Supervisor + ASM', min=Decimal('1000000'), max=Decimal('2999999'), chain='supervisor,asm', order=2, active=True),
        dict(name='Sup + ASM + AVP/GM', min=Decimal('3000000'), max=None, chain='supervisor,asm,avp_or_gm', order=3, active=True),
    ]
    created, updated = 0, 0
    for s in seeds:
        qs = ProposalApprovalTier.objects.filter(min_amount_php=s['min'], chain=s['chain'])
        if s['max'] is None:
            qs = qs.filter(max_amount_php__isnull=True)
        else:
            qs = qs.filter(max_amount_php=s['max'])
        obj = qs.first()
        if obj:
            obj.name = s['name']
            obj.order = s['order']
            obj.active = s['active']
            obj.save()
            updated += 1
        else:
            ProposalApprovalTier.objects.create(
                name=s['name'],
                min_amount_php=s['min'],
                max_amount_php=s['max'],
                chain=s['chain'],
                order=s['order'],
                active=s['active'],
            )
            created += 1
    messages.success(request, f'Default tiers seeded. Created: {created}, Updated: {updated}.')
    return redirect('approval_tier_list')

def log_sales_activity(proposal, user):
    # Find or create 'Proposal' activity type
    activity_type, _ = ActivityType.objects.get_or_create(
        name='Proposals',
        defaults={'icon': 'fas fa-file-alt', 'color': 'info'}
    )
    
    SalesActivity.objects.create(
        title=f"Sent Proposal: {proposal.proposal_number}",
        description=f"Sent proposal regarding {proposal.subject} to {proposal.customer.email}",
        activity_type=activity_type,
        salesperson=user,
        customer=proposal.customer,
        status='completed',
        priority='high',
        scheduled_start=timezone.now(),
        scheduled_end=timezone.now(),
        actual_start=timezone.now()
    )

def update_sales_funnel(proposal):
    # Determine PHP amounts for Sales Funnel (which tracks in PHP)
    retail_php = proposal.quoted_amount_php
    cost_php = proposal.quoted_cost_php * Decimal('1.05')

    # Try to find a funnel entry linked to this proposal
    funnel = SalesFunnel.objects.filter(proposal=proposal).first()
    
    if funnel:
        # Update existing linked funnel entry
        funnel.retail = retail_php
        funnel.cost = cost_php
        funnel.requirement_description = proposal.subject
        funnel.save()
    else:
        # Create new funnel entry linked to this proposal
        SalesFunnel.objects.create(
            date_created=proposal.date,
            company_name=proposal.customer.company_name,
            requirement_description=proposal.subject,
            cost=cost_php,
            retail=retail_php,
            stage='quoted', # Pink Funnel
            salesperson=proposal.created_by,
            customer=proposal.customer,
            deal_outcome='active',
            proposal=proposal
        )
