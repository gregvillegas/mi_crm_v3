import threading
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponseForbidden
from django.utils import timezone
from django.db.models import Max
from django.core.files.base import ContentFile
from django.conf import settings
from .models import Campaign, CampaignRecipient, OptOut, MediaLibraryAsset, CampaignAsset, Announcement, AnnouncementView
from .forms import CampaignForm, UnsubscribeForm, CampaignAssetFormSet, MediaLibraryAssetForm, AnnouncementForm
from .rendering import render_campaign_html
from customers.models import Customer, CustomerNote
from lead_generation.models import Lead, LeadActivity


def can_manage_media_library(user):
    return user.role in ['admin', 'marketing']


def can_view_media_library(user):
    return user.role in ['admin', 'marketing']


def can_manage_announcements(user):
    """Who may create/edit/delete announcements & events."""
    return getattr(user, 'is_authenticated', False) and user.role in ['admin', 'marketing']


# Roles that may not access mass-mailing campaigns at all. Purchasing staff and
# operations managers have no business with outbound marketing campaigns; the
# company-wide announcement feed remains visible to them.
CAMPAIGN_BLOCKED_ROLES = {'purchasing', 'purchasing_supervisor', 'operation_mgr'}


def can_access_campaigns(user):
    """Whether the user may open campaign pages (list, create, detail, ...)."""
    return getattr(user, 'is_authenticated', False) and getattr(user, 'role', None) not in CAMPAIGN_BLOCKED_ROLES


def active_announcements_qs():
    """Active announcements/events, newest first — the company-wide feed source."""
    return Announcement.objects.filter(is_active=True).select_related('created_by')


def unread_announcement_count(user):
    """
    Number of active announcements created after the user's last_seen_at.
    If the user has never viewed the feed, all active announcements are unread.
    """
    if not getattr(user, 'is_authenticated', False):
        return 0
    qs = Announcement.objects.filter(is_active=True)
    view = AnnouncementView.objects.filter(user=user).first()
    if view and view.last_seen_at:
        return qs.filter(created_at__gt=view.last_seen_at).count()
    return qs.count()


def mark_announcements_seen(user):
    """Stamp the user's last_seen_at = now(), clearing their unread badge."""
    if not getattr(user, 'is_authenticated', False):
        return
    AnnouncementView.objects.update_or_create(
        user=user,
        defaults={'last_seen_at': timezone.now()},
    )


def sync_selected_library_assets(campaign, selected_ids, user):
    selected_ids = {int(i) for i in selected_ids if str(i).isdigit()}
    existing = {asset.library_asset_id: asset for asset in campaign.assets.filter(library_asset__isnull=False)}

    # Delete deselected library-based assets
    for library_id, asset in list(existing.items()):
        if library_id not in selected_ids:
            asset.delete()

    # Add newly selected library assets
    max_sort = campaign.assets.aggregate(max_sort=Max('sort_order'))['max_sort'] or 0
    new_library_ids = [library_id for library_id in selected_ids if library_id not in existing]
    for offset, library_asset in enumerate(MediaLibraryAsset.objects.filter(id__in=new_library_ids, is_active=True), start=1):
        library_asset.file.open('rb')
        content = library_asset.file.read()
        library_asset.file.close()
        filename = os.path.basename(library_asset.file.name)
        campaign_asset = CampaignAsset(
            campaign=campaign,
            library_asset=library_asset,
            display_name=library_asset.title,
            embed_inline=True,
            sort_order=max_sort + offset,
            uploaded_by=user,
        )
        campaign_asset.file.save(filename, ContentFile(content), save=True)


def serialize_recipients_for_textarea(campaign):
    lines = []
    for recipient in campaign.recipients.all().order_by('email'):
        lines.append(', '.join([
            recipient.display_company_name or '',
            recipient.display_contact_name or '',
            recipient.email or '',
            recipient.position or '',
        ]).rstrip(', '))
    return '\n'.join(lines)


def get_initial_form_values(campaign):
    initial_customers = Customer.objects.filter(id__in=campaign.recipients.exclude(customer__isnull=True).values_list('customer_id', flat=True))
    initial_leads = Lead.objects.filter(id__in=campaign.recipients.exclude(lead__isnull=True).values_list('lead_id', flat=True))
    recipient_lines = serialize_recipients_for_textarea(campaign)
    return {
        'customers': initial_customers,
        'leads': initial_leads,
        'manual_recipients': recipient_lines if campaign.recipient_mode == 'manual' else '',
        'csv_paste_recipients': recipient_lines if campaign.recipient_mode == 'csv' else '',
    }


def get_recipient_context(recipient):
    return {
        'contact_name': recipient.display_contact_name or 'Valued Contact',
        'company_name': recipient.display_company_name or 'Sample Company Inc.',
    }


def build_recipient_payloads(form):
    mode = form.cleaned_data.get('recipient_mode') or 'crm'
    opted_out_emails = {email.lower() for email in OptOut.objects.values_list('email', flat=True)}
    payloads = []
    seen = set()
    skipped_opt_out = 0

    if mode == 'crm':
        for customer in form.cleaned_data['customers']:
            email = (customer.email or '').strip().lower()
            if not email:
                continue
            if email in opted_out_emails:
                skipped_opt_out += 1
                continue
            if email in seen:
                continue
            seen.add(email)
            payloads.append({
                'customer': customer,
                'company_name': customer.company_name or '',
                'contact_name': customer.contact_person_name or '',
                'position': getattr(customer, 'contact_person_position', '') or '',
                'email': email,
                'source_type': 'customer',
            })
    elif mode == 'crm_leads':
        for lead in form.cleaned_data['leads']:
            email = (lead.email or '').strip().lower()
            if not email:
                continue
            if email in opted_out_emails:
                skipped_opt_out += 1
                continue
            if email in seen:
                continue
            seen.add(email)
            payloads.append({
                'customer': None,
                'lead': lead,
                'company_name': lead.company_name or '',
                'contact_name': lead.full_name or '',
                'position': lead.job_title or '',
                'email': email,
                'source_type': 'lead',
            })
    else:
        parsed = form.cleaned_data.get('parsed_csv_recipients') if mode == 'csv' else form.cleaned_data.get('parsed_manual_recipients')
        for item in parsed or []:
            email = (item.get('email') or '').strip().lower()
            if not email:
                continue
            if email in opted_out_emails:
                skipped_opt_out += 1
                continue
            if email in seen:
                continue
            seen.add(email)
            payloads.append({
                'customer': None,
                'lead': None,
                'company_name': item.get('company_name', ''),
                'contact_name': item.get('contact_name', ''),
                'position': item.get('position', ''),
                'email': email,
                'source_type': item.get('source_type', mode),
            })

    return payloads, skipped_opt_out


def save_campaign_recipients(campaign, recipient_payloads):
    campaign.recipients.all().delete()
    for payload in recipient_payloads:
        CampaignRecipient.objects.create(
            campaign=campaign,
            customer=payload['customer'],
            lead=payload.get('lead'),
            company_name=payload['company_name'],
            contact_name=payload['contact_name'],
            position=payload['position'],
            email=payload['email'],
            source_type=payload['source_type'],
        )
    campaign.update_counts()

def get_allowed_campaigns(user):
    """Returns a queryset of campaigns the user is allowed to see based on their role."""
    if not can_access_campaigns(user):
        return Campaign.objects.none()
    if user.role == 'salesperson':
        return Campaign.objects.filter(created_by=user)
        
    elif user.role == 'supervisor':
        member_ids = [user.id]
        for group in user.managed_groups.all():
            member_ids.extend(group.members.values_list('user_id', flat=True))
        return Campaign.objects.filter(created_by_id__in=member_ids)
        
    elif user.role == 'teamlead':
        member_ids = [user.id]
        for group in user.led_groups.all():
            member_ids.extend(group.members.values_list('user_id', flat=True))
        return Campaign.objects.filter(created_by_id__in=member_ids)
        
    elif user.role == 'asm':
        member_ids = [user.id]
        for team in user.asm_teams.all():
            for group in team.groups.all():
                member_ids.extend(group.members.values_list('user_id', flat=True))
                if group.supervisor:
                    member_ids.append(group.supervisor.id)
        return Campaign.objects.filter(created_by_id__in=member_ids)
        
    elif user.role == 'avp':
        member_ids = [user.id]
        for team in user.managed_teams.all():
            for group in team.groups.all():
                member_ids.extend(group.members.values_list('user_id', flat=True))
                if group.supervisor:
                    member_ids.append(group.supervisor.id)
        return Campaign.objects.filter(created_by_id__in=member_ids)
        
    else:
        # Admins, Presidents, VPs, GMs can see all
        return Campaign.objects.all()

@login_required
def campaign_list(request):
    if not can_access_campaigns(request.user):
        return HttpResponseForbidden("You don't have permission to access campaigns.")
    campaigns = get_allowed_campaigns(request.user).order_by('-created_at')
    return render(request, 'mass_mailing/campaign_list.html', {'campaigns': campaigns})


@login_required
def media_library(request):
    if not can_view_media_library(request.user):
        messages.error(request, "You don't have permission to access the Media Library.")
        return redirect('mass_mailing:campaign_list')

    assets = MediaLibraryAsset.objects.all().order_by('-created_at')
    library_form = MediaLibraryAssetForm()

    if request.method == 'POST':
        if 'upload_library_media' in request.POST:
            if not can_manage_media_library(request.user):
                messages.error(request, "You don't have permission to upload media.")
                return redirect('mass_mailing:media_library')
            library_form = MediaLibraryAssetForm(request.POST, request.FILES)
            if library_form.is_valid():
                media = library_form.save(commit=False)
                media.uploaded_by = request.user
                media.save()
                messages.success(request, f'Media "{media.title}" uploaded successfully.')
                return redirect('mass_mailing:media_library')

        elif 'delete_media' in request.POST:
            if not can_manage_media_library(request.user):
                messages.error(request, "You don't have permission to delete media.")
                return redirect('mass_mailing:media_library')
            asset = get_object_or_404(MediaLibraryAsset, pk=request.POST.get('asset_id'))
            asset.delete()
            messages.success(request, "Media deleted from the library.")
            return redirect('mass_mailing:media_library')

        elif 'toggle_media_status' in request.POST:
            if not can_manage_media_library(request.user):
                messages.error(request, "You don't have permission to update media.")
                return redirect('mass_mailing:media_library')
            asset = get_object_or_404(MediaLibraryAsset, pk=request.POST.get('asset_id'))
            asset.is_active = not asset.is_active
            asset.save(update_fields=['is_active'])
            messages.success(request, f'"{asset.title}" is now {"active" if asset.is_active else "inactive"}.')
            return redirect('mass_mailing:media_library')

    return render(request, 'mass_mailing/media_library.html', {
        'assets': assets,
        'library_form': library_form,
        'can_manage_media_library': can_manage_media_library(request.user),
        'can_view_media_library': can_view_media_library(request.user),
    })

@login_required
def campaign_create(request):
    if not can_access_campaigns(request.user):
        return HttpResponseForbidden("You don't have permission to create campaigns.")
    library_assets = MediaLibraryAsset.objects.filter(is_active=True)
    selected_library_ids = []
    if request.method == 'POST':
        if 'upload_library_media' in request.POST and can_manage_media_library(request.user):
            library_form = MediaLibraryAssetForm(request.POST, request.FILES)
            form = CampaignForm(user=request.user)
            asset_formset = CampaignAssetFormSet(prefix='assets')
            if library_form.is_valid():
                media = library_form.save(commit=False)
                media.uploaded_by = request.user
                media.save()
                messages.success(request, f'Media "{media.title}" uploaded to the library.')
                return redirect('mass_mailing:campaign_create')
            return render(request, 'mass_mailing/campaign_form.html', {
                'form': form,
                'asset_formset': asset_formset,
                'library_form': library_form,
                'library_assets': library_assets,
                'selected_library_ids': selected_library_ids,
                'can_manage_media_library': can_manage_media_library(request.user),
                'can_view_media_library': can_view_media_library(request.user),
            })
        form = CampaignForm(request.POST, user=request.user)
        asset_formset = CampaignAssetFormSet(request.POST, request.FILES, prefix='assets')
        selected_library_ids = request.POST.getlist('library_assets')
        if form.is_valid() and asset_formset.is_valid():
            recipient_payloads, skipped_opt_out = build_recipient_payloads(form)
            if not recipient_payloads:
                form.add_error(None, 'No valid recipients remain after opt-out filtering. Please review your list.')
            else:
                campaign = form.save(commit=False)
                campaign.created_by = request.user
                campaign.save()
                asset_formset.instance = campaign
                assets = asset_formset.save(commit=False)
                for asset in assets:
                    asset.campaign = campaign
                    asset.uploaded_by = request.user
                    asset.save()
                for obj in asset_formset.deleted_objects:
                    obj.delete()
                sync_selected_library_assets(campaign, selected_library_ids, request.user)
                save_campaign_recipients(campaign, recipient_payloads)
                
                success_msg = f"Campaign '{campaign.name}' created with {campaign.total_recipients} valid recipients."
                if skipped_opt_out:
                    success_msg += f" {skipped_opt_out} opted-out recipient(s) were excluded."
                messages.success(request, success_msg)
                return redirect('mass_mailing:campaign_detail', pk=campaign.pk)
    else:
        form = CampaignForm(user=request.user)
        asset_formset = CampaignAssetFormSet(prefix='assets')
        library_form = MediaLibraryAssetForm()
        
    if request.method != 'POST' or 'upload_library_media' not in request.POST:
        library_form = locals().get('library_form', MediaLibraryAssetForm())

    return render(request, 'mass_mailing/campaign_form.html', {
        'form': form,
        'asset_formset': asset_formset,
        'library_form': library_form,
        'library_assets': library_assets,
        'selected_library_ids': selected_library_ids,
        'can_manage_media_library': can_manage_media_library(request.user),
        'can_view_media_library': can_view_media_library(request.user),
    })

@login_required
def campaign_detail(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    
    if not get_allowed_campaigns(request.user).filter(pk=pk).exists():
        return HttpResponseForbidden("You are not allowed to view this campaign.")
        
    recipients = campaign.recipients.all()
    interested_count = campaign.recipients.filter(interested_at__isnull=False).count()
    
    return render(request, 'mass_mailing/campaign_detail.html', {
        'campaign': campaign,
        'recipients': recipients,
        'interested_count': interested_count,
    })

@login_required
def campaign_edit(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    library_assets = MediaLibraryAsset.objects.filter(is_active=True)
    selected_library_ids = list(campaign.assets.filter(library_asset__isnull=False).values_list('library_asset_id', flat=True))
    
    if not get_allowed_campaigns(request.user).filter(pk=pk).exists():
        return HttpResponseForbidden("You are not allowed to edit this campaign.")
        
    if campaign.status not in ['draft', 'scheduled']:
        messages.error(request, "You can only edit campaigns that are in Draft or Scheduled status.")
        return redirect('mass_mailing:campaign_detail', pk=pk)
        
    if request.method == 'POST':
        if 'upload_library_media' in request.POST and can_manage_media_library(request.user):
            library_form = MediaLibraryAssetForm(request.POST, request.FILES)
            form = CampaignForm(instance=campaign, user=request.user, initial=get_initial_form_values(campaign))
            asset_formset = CampaignAssetFormSet(instance=campaign, prefix='assets')
            if library_form.is_valid():
                media = library_form.save(commit=False)
                media.uploaded_by = request.user
                media.save()
                messages.success(request, f'Media "{media.title}" uploaded to the library.')
                return redirect('mass_mailing:campaign_edit', pk=campaign.pk)
            return render(request, 'mass_mailing/campaign_form.html', {
                'form': form,
                'campaign': campaign,
                'asset_formset': asset_formset,
                'library_form': library_form,
                'library_assets': library_assets,
                'selected_library_ids': selected_library_ids,
                'can_manage_media_library': can_manage_media_library(request.user),
                'can_view_media_library': can_view_media_library(request.user),
            })
        form = CampaignForm(request.POST, instance=campaign, user=request.user)
        asset_formset = CampaignAssetFormSet(request.POST, request.FILES, instance=campaign, prefix='assets')
        selected_library_ids = request.POST.getlist('library_assets')
        if form.is_valid() and asset_formset.is_valid():
            recipient_payloads, skipped_opt_out = build_recipient_payloads(form)
            if not recipient_payloads:
                form.add_error(None, 'No valid recipients remain after opt-out filtering. Please review your list.')
            else:
                campaign = form.save()
                assets = asset_formset.save(commit=False)
                for asset in assets:
                    asset.campaign = campaign
                    if not asset.uploaded_by_id:
                        asset.uploaded_by = request.user
                    asset.save()
                for obj in asset_formset.deleted_objects:
                    obj.delete()
                sync_selected_library_assets(campaign, selected_library_ids, request.user)
                
                if campaign.status == 'draft':
                    save_campaign_recipients(campaign, recipient_payloads)
                
                success_msg = f"Campaign '{campaign.name}' has been updated."
                if skipped_opt_out:
                    success_msg += f" {skipped_opt_out} opted-out recipient(s) were excluded."
                messages.success(request, success_msg)
                return redirect('mass_mailing:campaign_detail', pk=campaign.pk)
    else:
        # Pre-populate selected customers
        form = CampaignForm(instance=campaign, user=request.user, initial=get_initial_form_values(campaign))
        asset_formset = CampaignAssetFormSet(instance=campaign, prefix='assets')
        library_form = MediaLibraryAssetForm()
        
    if request.method != 'POST' or 'upload_library_media' not in request.POST:
        library_form = locals().get('library_form', MediaLibraryAssetForm())

    return render(request, 'mass_mailing/campaign_form.html', {
        'form': form,
        'campaign': campaign,
        'asset_formset': asset_formset,
        'library_form': library_form,
        'library_assets': library_assets,
        'selected_library_ids': selected_library_ids,
        'can_manage_media_library': can_manage_media_library(request.user),
        'can_view_media_library': can_view_media_library(request.user),
    })

@login_required
def campaign_cancel(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    
    if not get_allowed_campaigns(request.user).filter(pk=pk).exists():
        return HttpResponseForbidden("You are not allowed to cancel this campaign.")
        
    if campaign.status in ['completed', 'cancelled']:
        messages.error(request, "This campaign cannot be cancelled anymore.")
        return redirect('mass_mailing:campaign_detail', pk=pk)
        
    if request.method == 'POST':
        # If it was a draft, just delete it entirely to clean up DB
        if campaign.status == 'draft':
            campaign.delete()
            messages.success(request, "Draft campaign deleted successfully.")
            return redirect('mass_mailing:campaign_list')
            
        # Otherwise, mark as cancelled so the worker stops sending
        campaign.status = 'cancelled'
        campaign.save()
        messages.success(request, "Campaign has been cancelled. No further emails will be sent.")
        return redirect('mass_mailing:campaign_detail', pk=pk)
        
    return render(request, 'mass_mailing/campaign_cancel.html', {'campaign': campaign})

@login_required
def campaign_preview(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    
    if not get_allowed_campaigns(request.user).filter(pk=pk).exists():
        return HttpResponseForbidden("You are not allowed to preview this campaign.")
        
    # Get a sample recipient to preview
    sample_recipient = campaign.recipients.first()
    
    context_dict = {}
    if sample_recipient:
        context_dict = get_recipient_context(sample_recipient)
    else:
        context_dict = {
            'contact_name': 'John Doe',
            'company_name': 'Sample Company Inc.',
        }
        
    rendered_body = render_campaign_html(campaign, context_dict, preview=True)
    if campaign.include_unsubscribe:
        footer = """
        <div class="email-footer">
            <div style="margin-bottom: 14px;">
                <a href="#" style="display:inline-block;background:#16a34a;color:#ffffff;text-decoration:none;padding:10px 18px;border-radius:6px;font-weight:700;font-size:14px;">Interested - Send More Information</a>
            </div>
            This email was sent to you because you are a valued contact of <strong>Micro Image International Corp.</strong><br>
            In accordance with the Data Privacy Act of 2012 (R.A. 10173), you have the right to opt-out of receiving these marketing communications.<br><br>
            <a href="#">Click here to Unsubscribe safely</a>
        </div>
        """
        rendered_body = (rendered_body or '') + footer
    
    return render(request, 'mass_mailing/campaign_preview.html', {
        'campaign': campaign,
        'rendered_body': rendered_body
    })

@login_required
def campaign_send(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    
    if not get_allowed_campaigns(request.user).filter(pk=pk).exists():
        return HttpResponseForbidden("You are not allowed to send this campaign.")
        
    if campaign.status != 'draft':
        messages.warning(request, "This campaign is already scheduled or sending.")
        return redirect('mass_mailing:campaign_detail', pk=pk)
        
    # Update status to scheduled
    campaign.status = 'scheduled'
    if not campaign.scheduled_for:
        campaign.scheduled_for = timezone.now()
    campaign.save()
    
    messages.success(request, "Campaign has been queued for sending. It will be processed in the background.")
    
    # In a real production environment, a Cron job or Celery worker would pick this up.
    # For demonstration/sandbox purposes, we will trigger a background thread to process it.
    from django.core.management import call_command
    
    # If the campaign is scheduled for the future, we need to wait.
    # In a proper setup, a cron job runs every minute to check this.
    # Here, we'll spawn a thread that waits until the scheduled time.
    def run_worker():
        try:
            campaign.refresh_from_db()
            if campaign.status == 'cancelled':
                return
                
            # Calculate how long to wait
            now = timezone.now()
            if campaign.scheduled_for and campaign.scheduled_for > now:
                wait_seconds = (campaign.scheduled_for - now).total_seconds()
                if wait_seconds > 0:
                    import time
                    time.sleep(wait_seconds)
            
            call_command('process_mail_queue')
        except Exception as e:
            print(f"Background worker error: {e}")
            
    thread = threading.Thread(target=run_worker)
    thread.daemon = True
    thread.start()
    
    return redirect('mass_mailing:campaign_detail', pk=pk)

def unsubscribe(request, recipient_id):
    recipient = get_object_or_404(CampaignRecipient, id=recipient_id)
    
    if request.method == 'POST':
        form = UnsubscribeForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            reason = form.cleaned_data['reason']
            
            # Record opt-out
            OptOut.objects.get_or_create(
                email=email,
                defaults={'customer': recipient.customer, 'reason': reason}
            )
            
            # Update recipient status if not already sent
            if recipient.status == 'pending':
                recipient.status = 'opted_out'
                recipient.save()
                recipient.campaign.update_counts()
                
            return render(request, 'mass_mailing/unsubscribe_success.html', {'email': email})
    else:
        form = UnsubscribeForm(initial={'email': recipient.email})
        
    return render(request, 'mass_mailing/unsubscribe.html', {'form': form, 'recipient': recipient})


def interested(request, recipient_id):
    recipient = get_object_or_404(CampaignRecipient, id=recipient_id)
    campaign = recipient.campaign

    # Always record the click timestamp
    if recipient.interested_at is None:
        recipient.interested_at = timezone.now()
        recipient.save(update_fields=['interested_at'])

        ip_address = request.META.get('REMOTE_ADDR', '')
        user_agent = request.META.get('HTTP_USER_AGENT', '')

        note_text = (
            f"Recipient clicked Interested from campaign '{campaign.name}' "
            f"({campaign.subject}) on {timezone.localtime(recipient.interested_at).strftime('%Y-%m-%d %H:%M')}."
        )
        if ip_address:
            note_text += f" IP: {ip_address}."
        if user_agent:
            note_text += f" UA: {user_agent}."

        if recipient.lead_id:
            LeadActivity.objects.create(
                lead=recipient.lead,
                activity_type='note',
                title='Interested (Email Campaign)',
                description=note_text,
                notes=note_text,
                performed_by=campaign.created_by,
                created_by=campaign.created_by,
                outcome='interested',
            )
        elif recipient.customer_id:
            CustomerNote.objects.create(
                customer=recipient.customer,
                author=campaign.created_by,
                content=note_text,
            )

    # Show the inquiry form instead of immediately redirecting
    return render(request, 'mass_mailing/interested_form.html', {
        'recipient': recipient,
        'campaign': campaign,
    })


def submit_inquiry(request, recipient_id):
    """Handle inquiry form submission from interested recipients"""
    recipient = get_object_or_404(CampaignRecipient, id=recipient_id)
    campaign = recipient.campaign

    if request.method == 'POST':
        inquiry_name = request.POST.get('name', '').strip()
        inquiry_company = request.POST.get('company', '').strip()
        inquiry_email = request.POST.get('email', '').strip()
        inquiry_phone = request.POST.get('phone', '').strip()
        inquiry_message = request.POST.get('message', '').strip()

        if inquiry_name and inquiry_email and inquiry_message:
            # Send email to the campaign creator (AE)
            from django.core.mail import EmailMessage
            
            subject = f'[CRM] Inquiry from {inquiry_name} via "{campaign.name}" Campaign'
            body = f"""Hello {campaign.created_by.get_full_name() or campaign.created_by.username},

You have received a new inquiry from your email campaign "{campaign.name}".

------------------------------------------------------------
INQUIRY DETAILS
------------------------------------------------------------
Name         : {inquiry_name}
Company      : {inquiry_company or '—'}
Email        : {inquiry_email}
Phone        : {inquiry_phone or '—'}
Campaign     : {campaign.name} ({campaign.subject})
Submitted At : {timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M')}

MESSAGE:
{inquiry_message}
------------------------------------------------------------

Original recipient: {recipient.email} ({recipient.display_company_name})

This inquiry was submitted via the "Interested - Send More Information" button in your email campaign.
Please follow up with the recipient directly.

—
{getattr(settings, 'COMPANY_NAME', 'Micro Image International Corp.')}
"""

            try:
                EmailMessage(
                    subject=subject,
                    body=body,
                    from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@microimageph.com'),
                    to=[campaign.created_by.email] if campaign.created_by.email else [],
                    reply_to=[inquiry_email],
                ).send(fail_silently=False)
            except Exception as e:
                # Log but don't show error to the public user
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f'Failed to send inquiry email for campaign {campaign.pk}: {e}')

            # Store inquiry as a note if customer/lead exists
            inquiry_note = (
                f"Inquiry submitted via '{campaign.name}' campaign:\n"
                f"Name: {inquiry_name}\n"
                f"Company: {inquiry_company or '—'}\n"
                f"Email: {inquiry_email}\n"
                f"Phone: {inquiry_phone or '—'}\n"
                f"Message: {inquiry_message}"
            )
            if recipient.lead_id:
                LeadActivity.objects.create(
                    lead=recipient.lead,
                    activity_type='inquiry',
                    title=f'Inquiry from {inquiry_name}',
                    description=inquiry_note,
                    notes=inquiry_note,
                    performed_by=campaign.created_by,
                    created_by=campaign.created_by,
                    outcome='interested',
                )
            elif recipient.customer_id:
                CustomerNote.objects.create(
                    customer=recipient.customer,
                    author=campaign.created_by,
                    content=inquiry_note,
                )

            return render(request, 'mass_mailing/interested_form_sent.html', {
                'campaign': campaign,
                'inquiry_name': inquiry_name,
                'company_website': getattr(settings, 'COMPANY_WEBSITE_URL', 'https://www.microimageph.com'),
                'company_phone': getattr(settings, 'COMPANY_OFFICE_PHONE', '8-840-4323'),
                'company_address': getattr(settings, 'COMPANY_ADDRESS', 'Makati City, Philippines'),
            })

        else:
            messages.error(request, 'Please fill in all required fields (Name, Email, Message).')
            return render(request, 'mass_mailing/interested_form.html', {
                'recipient': recipient,
                'campaign': campaign,
                'form_data': request.POST,
            })

    # GET request — redirect back to form
    return redirect('mass_mailing:interested', recipient_id=recipient_id)


@login_required
def interested_recipients_list(request, pk):
    """Show all interested recipients for a campaign (staff only)"""
    campaign = get_object_or_404(Campaign, pk=pk)
    
    if not get_allowed_campaigns(request.user).filter(pk=pk).exists():
        return HttpResponseForbidden("You are not allowed to view this campaign.")
    
    interested_recipients = campaign.recipients.filter(
        interested_at__isnull=False
    ).order_by('-interested_at')
    
    return render(request, 'mass_mailing/interested_list.html', {
        'campaign': campaign,
        'interested_recipients': interested_recipients,
    })


# ---------------------------------------------------------------------------
# Announcements & Events (Marketing)
# ---------------------------------------------------------------------------
@login_required
def announcement_list(request):
    """List announcements & events. Read-only for non-managers is not needed
    (this page is only linked for marketing/admin), but we still gate it."""
    if not can_manage_announcements(request.user):
        messages.error(request, "You don't have access to announcements.")
        return redirect('mass_mailing:campaign_list')

    announcements = Announcement.objects.all().select_related('created_by')
    return render(request, 'mass_mailing/announcement_list.html', {
        'announcements': announcements,
        'can_manage_announcements': True,
    })


@login_required
def announcement_create(request):
    if not can_manage_announcements(request.user):
        messages.error(request, "You don't have permission to create announcements.")
        return redirect('mass_mailing:campaign_list')

    if request.method == 'POST':
        form = AnnouncementForm(request.POST)
        if form.is_valid():
            ann = form.save(commit=False)
            ann.created_by = request.user
            ann.save()
            messages.success(request, f'Announcement "{ann.title}" created.')
            return redirect('mass_mailing:announcement_list')
    else:
        form = AnnouncementForm()
    return render(request, 'mass_mailing/announcement_form.html', {
        'form': form,
        'title': 'New Announcement / Event',
    })


@login_required
def announcement_edit(request, pk):
    if not can_manage_announcements(request.user):
        messages.error(request, "You don't have permission to edit announcements.")
        return redirect('mass_mailing:campaign_list')

    announcement = get_object_or_404(Announcement, pk=pk)
    if request.method == 'POST':
        form = AnnouncementForm(request.POST, instance=announcement)
        if form.is_valid():
            form.save()
            messages.success(request, f'Announcement "{announcement.title}" updated.')
            return redirect('mass_mailing:announcement_list')
    else:
        form = AnnouncementForm(instance=announcement)
    return render(request, 'mass_mailing/announcement_form.html', {
        'form': form,
        'title': 'Edit Announcement / Event',
        'announcement': announcement,
    })


@login_required
def announcement_delete(request, pk):
    if not can_manage_announcements(request.user):
        messages.error(request, "You don't have permission to delete announcements.")
        return redirect('mass_mailing:campaign_list')

    announcement = get_object_or_404(Announcement, pk=pk)
    if request.method == 'POST':
        title = announcement.title
        announcement.delete()
        messages.success(request, f'Announcement "{title}" deleted.')
    return redirect('mass_mailing:announcement_list')


@login_required
def announcement_toggle(request, pk):
    if not can_manage_announcements(request.user):
        messages.error(request, "You don't have permission to update announcements.")
        return redirect('mass_mailing:campaign_list')

    announcement = get_object_or_404(Announcement, pk=pk)
    if request.method == 'POST':
        announcement.is_active = not announcement.is_active
        announcement.save(update_fields=['is_active'])
        state = 'shown' if announcement.is_active else 'hidden'
        messages.success(request, f'"{announcement.title}" is now {state}.')
    return redirect('mass_mailing:announcement_list')


@login_required
def announcement_feed(request):
    """
    Company-wide, read-only feed of Marketing announcements & events.
    Visible to ALL authenticated users. Opening it marks announcements as seen
    (clears the notification-bell unread badge). Marketing/Admin also see Edit
    links (their existing manage views are unchanged).
    """
    type_filter = (request.GET.get('type') or '').strip()

    announcements = active_announcements_qs()
    if type_filter in dict(Announcement.TYPE_CHOICES):
        announcements = announcements.filter(announcement_type=type_filter)

    # Split events out so upcoming events can be surfaced/sorted by date.
    upcoming_events = (
        active_announcements_qs()
        .filter(announcement_type='event', event_date__gte=timezone.now())
        .order_by('event_date')
    )

    # Mark as seen AFTER computing the current unread state for this request.
    mark_announcements_seen(request.user)

    return render(request, 'mass_mailing/announcement_feed.html', {
        'announcements': announcements,
        'upcoming_events': upcoming_events,
        'type_filter': type_filter,
        'type_choices': Announcement.TYPE_CHOICES,
        'can_manage_announcements': can_manage_announcements(request.user),
    })
