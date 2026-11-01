"""
Views for Multi-Option Proposals.
Separated from views.py to keep the codebase clean and avoid breaking existing single-format logic.
"""
import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from customers.models import Customer

from .models import Proposal, ProposalOptionGroup, ProposalItem
from .multi_option_forms import (
    MultiOptionProposalForm,
    OptionGroupFormSet,
    MultiOptionAttachmentFormSet,
)
from .views import update_sales_funnel, notify_pending_approver, can_access_proposal
from customers.permissions import visible_customers_queryset


def _parse_option_items(request):
    """Parse the option_items_json payload into a list of item dicts."""
    try:
        items = json.loads(request.POST.get('option_items_json', '[]'))
    except (json.JSONDecodeError, TypeError):
        items = []
    return items if isinstance(items, list) else []


def _has_real_option_items(items_data):
    """True if at least one parsed item has a description or part number."""
    for item in items_data:
        if not isinstance(item, dict):
            continue
        if (item.get('description') or '').strip() or (item.get('part_number') or '').strip():
            return True
    return False


@login_required
def multi_option_proposal_create(request):
    """Create a new multi-option proposal."""
    customer_id = request.GET.get('customer')
    customer = None
    if customer_id:
        # Re-validate the deep-linked customer against the user's visible scope so
        # a crafted URL cannot pre-fill a customer the user is not allowed to use.
        customer = visible_customers_queryset(request.user).filter(pk=customer_id).first()
        if customer is None:
            messages.error(request, 'That customer is not available to you.')
            return redirect('proposal_list')

    if request.method == 'POST':
        form = MultiOptionProposalForm(request.POST, user=request.user)
        attach_formset = MultiOptionAttachmentFormSet(request.POST, request.FILES, prefix='attachments')

        parsed_items = _parse_option_items(request)
        if form.is_valid() and attach_formset.is_valid() and not _has_real_option_items(parsed_items):
            messages.error(request, 'A proposal must have at least one item.')
        elif form.is_valid() and attach_formset.is_valid():
            with transaction.atomic():
                proposal = form.save(commit=False)
                proposal.created_by = request.user
                proposal.save()

                # Parse option groups from POST (name fields: groups-0-name, groups-1-name, etc.)
                total_groups = int(request.POST.get('groups-TOTAL_FORMS', '0'))
                groups_saved = []
                for i in range(total_groups):
                    delete_flag = request.POST.get(f'groups-{i}-DELETE', '')
                    if delete_flag == 'on':
                        continue
                    group_name = request.POST.get(f'groups-{i}-name', '').strip()
                    if not group_name:
                        group_name = f'OPTION {len(groups_saved) + 1}'
                    group = ProposalOptionGroup.objects.create(
                        proposal=proposal,
                        name=group_name,
                        sort_order=len(groups_saved),
                    )
                    groups_saved.append(group)

                # Save items per group from JSON payload
                items_json = request.POST.get('option_items_json', '[]')
                try:
                    items_data = json.loads(items_json)
                except (json.JSONDecodeError, TypeError):
                    items_data = []

                for item_data in items_data:
                    group_index = item_data.get('group_index', 0)
                    if group_index < len(groups_saved):
                        group = groups_saved[group_index]
                        form_value = item_data.get('warranty', '') or ''
                        if proposal.use_availability_column:
                            item_avail, item_warr = form_value, ''
                        else:
                            item_avail, item_warr = '', form_value
                        ProposalItem.objects.create(
                            proposal=proposal,
                            option_group=group,
                            part_number=item_data.get('part_number', ''),
                            description=item_data.get('description', ''),
                            quantity=Decimal(str(item_data.get('quantity', '1') or '1').replace(',', '')),
                            unit_cost=Decimal(str(item_data.get('unit_cost', '0') or '0').replace(',', '')),
                            unit_price=Decimal(str(item_data.get('unit_price', '0') or '0').replace(',', '')),
                            availability=item_avail,
                            warranty=item_warr,
                            is_bundle=item_data.get('is_bundle', False),
                            bundled_items=item_data.get('bundled_items', ''),
                        )

                # Save attachments
                attachments = attach_formset.save(commit=False)
                for att in attachments:
                    att.proposal = proposal
                    att.uploaded_by = request.user
                    att.save()

                # Calculate totals (use highest option group subtotal)
                _calculate_multi_option_totals(proposal)
                proposal.ensure_approval_chain()
                update_sales_funnel(proposal)

                # Notify the first pending approver (e.g. AVP), if approval is required.
                notify_pending_approver(proposal, request=request)

                messages.success(request, 'Multi-option proposal created successfully.')
                return redirect('proposal_detail', pk=proposal.pk)
        else:
            # Re-render with errors visible
            group_formset = OptionGroupFormSet(request.POST, prefix='groups')
    else:
        initial_data = {}
        if customer:
            initial_data['customer'] = customer
        form = MultiOptionProposalForm(initial=initial_data, user=request.user)
        group_formset = OptionGroupFormSet(
            prefix='groups',
            initial=[
                {'name': 'OPTION 1'},
                {'name': 'OPTION 2'},
            ],
        )
        # Override TOTAL_FORMS to show the 2 initial groups
        group_formset.extra = 2
        attach_formset = MultiOptionAttachmentFormSet(prefix='attachments')

    return render(request, 'sales_proposals/multi_option_form.html', {
        'form': form,
        'group_formset': group_formset,
        'attach_formset': attach_formset,
        'title': 'Create Multi-Option Proposal',
        'proposal': None,
        'customer': customer,
        'existing_items_json': '[]',
    })


@login_required
def multi_option_proposal_update(request, pk):
    """Edit an existing multi-option proposal."""
    proposal = get_object_or_404(Proposal, pk=pk, is_multi_option=True)
    if not can_access_proposal(request.user, proposal):
        messages.error(request, 'You do not have access to that proposal.')
        return redirect('proposal_list')

    # Build existing items JSON for the template
    existing_items = []
    for group_idx, group in enumerate(proposal.option_groups.all()):
        for item in group.group_items.all():
            if proposal.use_availability_column:
                value_for_form = item.availability or ''
            else:
                value_for_form = item.warranty or ''
            existing_items.append({
                'group_index': group_idx,
                'part_number': item.part_number,
                'description': item.description,
                'quantity': str(item.quantity),
                'unit_cost': str(item.unit_cost),
                'unit_price': str(item.unit_price),
                'warranty': value_for_form,
                'is_bundle': item.is_bundle,
                'bundled_items': item.bundled_items,
            })

    if request.method == 'POST':
        form = MultiOptionProposalForm(request.POST, instance=proposal, user=request.user)
        group_formset = OptionGroupFormSet(request.POST, instance=proposal, prefix='groups')
        attach_formset = MultiOptionAttachmentFormSet(request.POST, request.FILES, instance=proposal, prefix='attachments')

        parsed_items = _parse_option_items(request)
        formsets_valid = form.is_valid() and group_formset.is_valid() and attach_formset.is_valid()
        if formsets_valid and not _has_real_option_items(parsed_items):
            messages.error(request, 'A proposal must have at least one item.')
        elif formsets_valid:
            with transaction.atomic():
                before_approval_version = Proposal.objects.filter(pk=proposal.pk).values_list('approval_version', flat=True).first() or 0
                proposal = form.save()

                # Delete old items (will be recreated from JSON)
                proposal.items.all().delete()

                # Save option groups
                groups_saved = []
                # Delete groups marked for deletion
                for gform in group_formset.deleted_forms:
                    if gform.instance.pk:
                        gform.instance.delete()

                for gform in group_formset:
                    if gform.cleaned_data and not gform.cleaned_data.get('DELETE', False):
                        group = gform.save(commit=False)
                        group.proposal = proposal
                        group.save()
                        groups_saved.append(group)

                # Recreate items from JSON
                items_json = request.POST.get('option_items_json', '[]')
                try:
                    items_data = json.loads(items_json)
                except (json.JSONDecodeError, TypeError):
                    items_data = []

                for item_data in items_data:
                    group_index = item_data.get('group_index', 0)
                    if group_index < len(groups_saved):
                        group = groups_saved[group_index]
                        form_value = item_data.get('warranty', '') or ''
                        if proposal.use_availability_column:
                            item_avail, item_warr = form_value, ''
                        else:
                            item_avail, item_warr = '', form_value
                        ProposalItem.objects.create(
                            proposal=proposal,
                            option_group=group,
                            part_number=item_data.get('part_number', ''),
                            description=item_data.get('description', ''),
                            quantity=Decimal(str(item_data.get('quantity', '1') or '1')),
                            unit_cost=Decimal(str(item_data.get('unit_cost', '0') or '0')),
                            unit_price=Decimal(str(item_data.get('unit_price', '0') or '0')),
                            availability=item_avail,
                            warranty=item_warr,
                            is_bundle=item_data.get('is_bundle', False),
                            bundled_items=item_data.get('bundled_items', ''),
                        )

                # Save attachments
                attachments = attach_formset.save(commit=False)
                for att in attachments:
                    att.proposal = proposal
                    att.uploaded_by = request.user
                    att.save()
                for obj in attach_formset.deleted_objects:
                    obj.delete()

                _calculate_multi_option_totals(proposal)
                proposal.ensure_approval_chain()
                update_sales_funnel(proposal)

                # Notify the current approver only when the workflow (re)started.
                proposal.refresh_from_db()
                if proposal.approval_required and proposal.approval_version != before_approval_version:
                    notify_pending_approver(proposal, request=request)

                messages.success(request, 'Multi-option proposal updated successfully.')
                return redirect('proposal_detail', pk=proposal.pk)
    else:
        form = MultiOptionProposalForm(instance=proposal, user=request.user)
        group_formset = OptionGroupFormSet(instance=proposal, prefix='groups')
        attach_formset = MultiOptionAttachmentFormSet(instance=proposal, prefix='attachments')

    return render(request, 'sales_proposals/multi_option_form.html', {
        'form': form,
        'group_formset': group_formset,
        'attach_formset': attach_formset,
        'title': 'Edit Multi-Option Proposal',
        'proposal': proposal,
        'customer': proposal.customer,
        'existing_items_json': json.dumps(existing_items, default=str),
    })


def _calculate_multi_option_totals(proposal):
    """
    For multi-option proposals, calculate totals using the HIGHEST option group subtotal.
    This determines the approval threshold and funnel sync value.
    """
    groups = proposal.option_groups.all()
    if not groups.exists():
        proposal.subtotal = Decimal('0')
        proposal.total_cost = Decimal('0')
        proposal.total_amount = Decimal('0')
        proposal.gross_profit = Decimal('0')
        proposal.approval_total_php = Decimal('0')
        proposal.approval_required = False
        proposal.save()
        return

    # Find the highest-value option group
    max_subtotal = Decimal('0')
    max_cost = Decimal('0')
    for group in groups:
        group_total = group.subtotal
        if group_total > max_subtotal:
            max_subtotal = group_total
            max_cost = group.total_cost

    proposal.subtotal = max_subtotal
    proposal.total_cost = max_cost

    # VAT: only applied when show_vat is enabled (12% on subtotal)
    if proposal.show_vat:
        proposal.tax_type = 'VAT'
        proposal.tax_rate = Decimal('12.00')
        proposal.tax_amount = (max_subtotal * Decimal('0.12')).quantize(Decimal('0.01'))
    else:
        proposal.tax_type = 'ZERO'
        proposal.tax_rate = Decimal('0')
        proposal.tax_amount = Decimal('0')

    proposal.total_amount = max_subtotal + proposal.tax_amount
    proposal.gross_profit = max_subtotal - (max_cost * Decimal('1.05'))

    # PHP equivalent for approval
    php_total = max_subtotal
    if proposal.currency == 'USD':
        rate = proposal.exchange_rate if proposal.exchange_rate > 0 else Decimal('1.0')
        php_total = max_subtotal * rate
    proposal.approval_total_php = php_total

    need = php_total >= Decimal('500000')
    proposal.approval_required = need
    if need and proposal.approval_status in ['not_required', 'approved', 'rejected']:
        proposal.approval_status = 'pending'
        proposal.approval_version = proposal.approval_version + 1

    proposal.save()
