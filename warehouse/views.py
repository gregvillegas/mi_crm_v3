from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from .forms import (
    BacklogReasonForm,
    DeliveryForm,
    DeliveryHistoryFilterForm,
    ScheduledDeliveryImportForm,
)
from .importers import (
    ScheduledDeliveryImportError,
    import_scheduled_delivery_file,
)
from .models import (
    BacklogReason,
    Delivery,
    get_transition_backlog_reason_error,
    get_transition_remarks_error,
)

# Column layout shared by the dashboard tables and the Excel export so the two
# never drift apart.
DELIVERY_COLUMNS = [
    'S.O. / SRF# / POR#',
    'CLIENT',
    'ITEM / PARTICULAR',
    'AREA',
    'DRIVER / STAFF',
    'VEHICLE PLATE',
    'AE',
    'REMARKS',
]

# Roles allowed to open the delivery board. Mirrors the navbar "Monitoring"
# dropdown gate so a hand-typed URL cannot widen access.
DELIVERY_VIEWER_ROLES = {
    'salesperson', 'avp', 'supervisor', 'teamlead', 'asm', 'admin',
    'president', 'gm', 'vp', 'technical_sales', 'techmgr', 'asst_techmgr',
    'warehouse',
}

# The Account Manager (salesperson) role may read the board but not export it.
DELIVERY_EXPORT_EXCLUDED_ROLES = {'salesperson'}

# Only the warehouse office role (and admins) may add or change deliveries.
DELIVERY_EDITOR_ROLES = {'warehouse', 'admin'}

HISTORY_PAGE_SIZE = 50


def _can_view_deliveries(user):
    return getattr(user, 'role', None) in DELIVERY_VIEWER_ROLES


def can_export_deliveries(user):
    """Everyone who can view the board, except the Account Manager role."""
    return (
        _can_view_deliveries(user)
        and getattr(user, 'role', None) not in DELIVERY_EXPORT_EXCLUDED_ROLES
    )


def can_edit_deliveries(user):
    """The warehouse office role owns the itinerary; admins keep a way in too."""
    return getattr(user, 'role', None) in DELIVERY_EDITOR_ROLES


def _selected_date(request):
    """Return the ?date=YYYY-MM-DD value, defaulting to today."""
    parsed = parse_date(request.GET.get('date') or '')
    return parsed or timezone.localdate()


def _backlog_summary():
    """Structured rollups for active backlog reporting."""
    backlog_qs = Delivery.objects.filter(
        status=Delivery.STATUS_FOR_SCHEDULE,
        is_backlog=True,
    ).select_related('backlog_reason')

    by_reason = list(
        backlog_qs.values('backlog_reason__name', 'backlog_reason__reason_group')
        .annotate(total=Count('id'))
        .order_by('-total', 'backlog_reason__name')
    )
    by_ae = list(
        backlog_qs.values('ae')
        .annotate(total=Count('id'))
        .order_by('-total', 'ae')
    )
    by_area = list(
        backlog_qs.values('area')
        .annotate(total=Count('id'))
        .order_by('-total', 'area')
    )
    repeat_items = list(
        backlog_qs.filter(backlog_count__gt=1)
        .order_by('-backlog_count', 'so_number')[:10]
    )

    return {
        'total': backlog_qs.count(),
        'by_reason': by_reason,
        'by_ae': by_ae,
        'by_area': by_area,
        'repeat_items': repeat_items,
    }


def _build_van_details(deliveries):
    """
    Group the scheduled deliveries by (vehicle plate, driver, warehouse staff)
    to generate the VAN DETAILS footer under the "Scheduled Delivery" table.
    """
    grouped = {}
    for delivery in deliveries:
        plate = (delivery.vehicle_plate or '').strip()
        driver = (delivery.driver_staff or '').strip()
        staff = (delivery.warehouse_staff_name or '').strip()
        if not plate and not driver and not staff:
            continue
        grouped.setdefault((plate, driver, staff), []).append(delivery.so_number)

    return [
        {
            'vehicle_plate': plate,
            'driver_staff': driver,
            'warehouse_staff': staff,
            'driver_staff_display': (
                f'{driver} - {staff}' if driver and staff else driver or staff
            ),
            'count': len(so_numbers),
            'so_numbers': so_numbers,
        }
        for (plate, driver, staff), so_numbers in grouped.items()
    ]


def _section_data(selected_date):
    """The three dashboard sections for the given day."""
    accomplished_date = selected_date - timedelta(days=1)
    return {
        'for_schedule': list(Delivery.objects.for_schedule().order_by('so_number')),
        'scheduled': list(
            Delivery.objects.scheduled_on(selected_date)
            .order_by('vehicle_plate', 'so_number')
        ),
        'accomplished': list(
            Delivery.objects.accomplished_on(accomplished_date).order_by('so_number')
        ),
        'accomplished_date': accomplished_date,
    }


@login_required
def delivery_dashboard(request):
    """Daily delivery itinerary board (three stacked sections)."""
    if not _can_view_deliveries(request.user):
        return HttpResponseForbidden(
            "You don't have permission to view warehouse deliveries."
        )

    selected_date = _selected_date(request)
    data = _section_data(selected_date)

    context = {
        'selected_date': selected_date,
        'accomplished_date': data['accomplished_date'],
        'for_schedule': data['for_schedule'],
        'scheduled': data['scheduled'],
        'accomplished': data['accomplished'],
        'van_details': _build_van_details(data['scheduled']),
        'backlog_summary': _backlog_summary(),
        'active_backlog_reasons': BacklogReason.objects.filter(is_active=True).order_by(
            'reason_group', 'sort_order', 'name'
        ),
        'can_edit': can_edit_deliveries(request.user),
        'can_export': can_export_deliveries(request.user),
    }
    return render(request, 'warehouse/delivery_dashboard.html', context)


@login_required
def delivery_history(request):
    """Past deliveries (Scheduled or Accomplished) for reporting/KPI."""
    if not _can_view_deliveries(request.user):
        return HttpResponseForbidden("You don't have access to the warehouse logs.")

    queryset = Delivery.objects.delivery_history()
    filter_form = DeliveryHistoryFilterForm(request.GET or None)
    if filter_form.is_valid():
        company = filter_form.cleaned_data['company']
        ae = filter_form.cleaned_data['ae']
        history_date = filter_form.cleaned_data['date']
        item = filter_form.cleaned_data['item']

        if company:
            queryset = queryset.filter(client__istartswith=company)
        if ae:
            queryset = queryset.filter(ae__istartswith=ae)
        if history_date:
            queryset = queryset.filter(
                Q(
                    status=Delivery.STATUS_ACCOMPLISHED,
                    accomplished_date=history_date,
                )
                | (
                    ~Q(status=Delivery.STATUS_ACCOMPLISHED)
                    & Q(scheduled_date=history_date)
                )
            )
        if item:
            queryset = queryset.filter(item__istartswith=item)

    paginator = Paginator(queryset, HISTORY_PAGE_SIZE)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    filter_params = request.GET.copy()
    filter_params.pop('page', None)

    return render(
        request,
        'warehouse/delivery_history.html',
        {
            'page_obj': page_obj,
            'total_count': paginator.count,
            'filter_form': filter_form,
            'filter_query': filter_params.urlencode(),
        },
    )


@login_required
def backlog_reason_list(request):
    """Warehouse-managed lookup list for backlog reason categories."""
    if not can_edit_deliveries(request.user):
        return HttpResponseForbidden(
            "You don't have permission to manage backlog categories."
        )

    reasons = BacklogReason.objects.order_by('reason_group', 'sort_order', 'name')
    form = BacklogReasonForm()

    return render(
        request,
        'warehouse/backlog_reason_list.html',
        {
            'reasons': reasons,
            'form': form,
            'page_title': 'Backlog Categories',
            'editing_reason': None,
        },
    )


@login_required
def backlog_reason_create(request):
    """Create a backlog reason category from the warehouse app."""
    if not can_edit_deliveries(request.user):
        return HttpResponseForbidden(
            "You don't have permission to manage backlog categories."
        )

    if request.method != 'POST':
        return redirect('warehouse:backlog_reason_list')

    form = BacklogReasonForm(request.POST)
    reasons = BacklogReason.objects.order_by('reason_group', 'sort_order', 'name')
    if form.is_valid():
        reason = form.save()
        messages.success(request, f'Backlog category "{reason.name}" was saved.')
        return redirect('warehouse:backlog_reason_list')

    return render(
        request,
        'warehouse/backlog_reason_list.html',
        {
            'reasons': reasons,
            'form': form,
            'page_title': 'Backlog Categories',
            'editing_reason': None,
        },
    )


@login_required
def backlog_reason_update(request, pk):
    """Edit an existing backlog reason category."""
    if not can_edit_deliveries(request.user):
        return HttpResponseForbidden(
            "You don't have permission to manage backlog categories."
        )

    reason = get_object_or_404(BacklogReason, pk=pk)
    reasons = BacklogReason.objects.order_by('reason_group', 'sort_order', 'name')

    if request.method == 'POST':
        form = BacklogReasonForm(request.POST, instance=reason)
        if form.is_valid():
            updated_reason = form.save()
            messages.success(
                request, f'Backlog category "{updated_reason.name}" was updated.'
            )
            return redirect('warehouse:backlog_reason_list')
    else:
        form = BacklogReasonForm(instance=reason)

    return render(
        request,
        'warehouse/backlog_reason_list.html',
        {
            'reasons': reasons,
            'form': form,
            'page_title': 'Backlog Categories',
            'editing_reason': reason,
        },
    )


@login_required
def delivery_timeline(request, pk):
    """Timeline of status/remark changes for one delivery."""
    if not _can_view_deliveries(request.user):
        return HttpResponseForbidden("You don't have access to the warehouse logs.")

    delivery = get_object_or_404(
        Delivery.objects.select_related('warehouse_staff', 'backlog_reason'),
        pk=pk,
    )
    events = delivery.events.select_related('changed_by').all()

    return render(
        request,
        'warehouse/delivery_timeline.html',
        {
            'delivery': delivery,
            'events': events,
            'can_edit': can_edit_deliveries(request.user),
        },
    )


@login_required
def delivery_create(request):
    """Add a delivery to the itinerary."""
    if not can_edit_deliveries(request.user):
        return HttpResponseForbidden(
            "You don't have permission to add warehouse deliveries."
        )

    if request.method == 'POST':
        form = DeliveryForm(request.POST)
        if form.is_valid():
            delivery = form.save(commit=False)
            delivery._event_user = request.user
            delivery.save()
            messages.success(request, f'Delivery {delivery.so_number} was added.')
            return redirect('warehouse:dashboard')
    else:
        form = DeliveryForm(initial={'status': Delivery.STATUS_FOR_SCHEDULE})

    return render(
        request,
        'warehouse/delivery_form.html',
        {'form': form, 'page_title': 'New Delivery'},
    )


@login_required
def delivery_update(request, pk):
    """Update a delivery (status, driver, plate, warehouse staff, ...)."""
    if not can_edit_deliveries(request.user):
        return HttpResponseForbidden(
            "You don't have permission to change warehouse deliveries."
        )

    delivery = get_object_or_404(Delivery, pk=pk)

    if request.method == 'POST':
        form = DeliveryForm(request.POST, instance=delivery)
        if form.is_valid():
            delivery = form.save(commit=False)
            delivery._event_user = request.user
            delivery.save()
            messages.success(request, f'Delivery {delivery.so_number} was updated.')
            return redirect('warehouse:dashboard')
    else:
        form = DeliveryForm(instance=delivery)

    return render(
        request,
        'warehouse/delivery_form.html',
        {'form': form, 'page_title': f'Edit {delivery.so_number}', 'delivery': delivery},
    )


@login_required
@require_POST
def delivery_update_status(request, pk):
    """Quickly flip a delivery status (e.g. Scheduled -> Accomplished)."""
    if not can_edit_deliveries(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    delivery = get_object_or_404(Delivery, pk=pk)
    new_status = request.POST.get('status')
    remarks = (request.POST.get('remarks') or '').strip()
    accomplished_date = None
    accomplished_date_raw = (request.POST.get('accomplished_date') or '').strip()
    backlog_reason = None
    backlog_reason_id = request.POST.get('backlog_reason') or ''

    if new_status not in dict(Delivery.STATUS_CHOICES):
        return JsonResponse({'error': 'Invalid status'}, status=400)
    if accomplished_date_raw:
        accomplished_date = parse_date(accomplished_date_raw)
        if accomplished_date is None:
            return JsonResponse({'error': 'Invalid accomplished date'}, status=400)
    if new_status == Delivery.STATUS_ACCOMPLISHED and accomplished_date is None:
        return JsonResponse(
            {'error': 'Please select the actual accomplished date.'},
            status=400,
        )
    if backlog_reason_id:
        backlog_reason = BacklogReason.objects.filter(pk=backlog_reason_id).first()
        if backlog_reason is None:
            return JsonResponse({'error': 'Invalid backlog category'}, status=400)

    error = get_transition_remarks_error(delivery.status, new_status, remarks)
    reason_error = get_transition_backlog_reason_error(
        delivery.status, new_status, backlog_reason
    )
    if error:
        return JsonResponse({'error': error}, status=400)
    if reason_error:
        return JsonResponse({'error': reason_error}, status=400)

    delivery.status = new_status
    if new_status == Delivery.STATUS_ACCOMPLISHED:
        delivery.accomplished_date = accomplished_date
    if remarks:
        delivery.remarks = remarks
        delivery._event_note = remarks
    if delivery.status == Delivery.STATUS_FOR_SCHEDULE and delivery.is_backlog:
        delivery.backlog_reason = backlog_reason or delivery.backlog_reason
    elif (
        request.POST.get('backlog_reason') is not None
        and delivery.status == Delivery.STATUS_FOR_SCHEDULE
    ):
        delivery.backlog_reason = backlog_reason
    elif backlog_reason is not None:
        delivery.backlog_reason = backlog_reason
    delivery._event_user = request.user
    delivery.save()

    return JsonResponse(
        {
            'success': True,
            'new_status': delivery.status,
            'remarks': delivery.remarks or '',
            'backlog_reason': delivery.backlog_reason_name,
            'accomplished_date': (
                delivery.accomplished_date.isoformat()
                if delivery.accomplished_date else ''
            ),
        }
    )


@login_required
def export_deliveries_excel(request):
    """
    Excel fallback: download the current dashboard as a workbook with one sheet
    per section, so offline users get the same itinerary they used to receive
    by email.
    """
    if not can_export_deliveries(request.user):
        return HttpResponseForbidden(
            "You don't have permission to export warehouse deliveries."
        )

    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    selected_date = _selected_date(request)
    data = _section_data(selected_date)

    sections = [
        ('FOR SCHEDULE', '7030A0', data['for_schedule']),
        ('SCHEDULED DELIVERY', 'FFC000', data['scheduled']),
        ('ACCOMPLISHED DELIVERY', '28A745', data['accomplished']),
    ]

    header_font = Font(bold=True, color='FFFFFF', size=10)
    thin = Side(style='thin', color='BFBFBF')
    border = Border(bottom=thin, top=thin, left=thin, right=thin)
    widths = [22, 34, 34, 18, 22, 16, 8, 40]

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    for title, colour, records in sections:
        ws = wb.create_sheet(title=title)
        fill = PatternFill(start_color=colour, end_color=colour, fill_type='solid')

        for col_idx, heading in enumerate(DELIVERY_COLUMNS, 1):
            cell = ws.cell(row=1, column=col_idx, value=heading)
            cell.font = header_font
            cell.fill = fill
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border

        for row_idx, delivery in enumerate(records, 2):
            values = [
                delivery.so_number,
                delivery.client,
                delivery.item,
                delivery.area or '',
                delivery.driver_staff or '',
                delivery.vehicle_plate or '',
                delivery.ae,
                delivery.remarks or '',
            ]
            for col_idx, value in enumerate(values, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.border = border
                cell.alignment = Alignment(vertical='top', wrap_text=(col_idx == 8))
                # Failed/pending rows keep the same bold-red emphasis as the board.
                if (
                    col_idx == 8
                    and delivery.status == Delivery.STATUS_FOR_SCHEDULE
                    and delivery.remarks
                ):
                    cell.font = Font(bold=True, color='FF0000')

        for col_idx, width in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = width
        ws.freeze_panes = 'A2'

        # VAN DETAILS footer under the Scheduled sheet.
        if title == 'SCHEDULED DELIVERY':
            footer_row = len(records) + 3
            ws.cell(row=footer_row, column=1, value='VAN DETAILS').font = Font(bold=True)
            ws.cell(row=footer_row + 1, column=1, value='VEHICLE PLATE').font = Font(bold=True)
            ws.cell(row=footer_row + 1, column=2, value='DRIVER / STAFF').font = Font(bold=True)
            ws.cell(row=footer_row + 1, column=3, value='ITEMS').font = Font(bold=True)
            for offset, van in enumerate(_build_van_details(data['scheduled']), 2):
                ws.cell(row=footer_row + offset, column=1, value=van['vehicle_plate'])
                ws.cell(row=footer_row + offset, column=2, value=van['driver_staff'])
                ws.cell(row=footer_row + offset, column=3, value=van['count'])

    stamp = timezone.localdate().strftime('%Y%m%d')
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="deliveries_{stamp}.xlsx"'
    wb.save(response)
    return response


@login_required
@require_POST
def import_scheduled_deliveries(request):
    """Upload scheduled deliveries from the legacy Excel/CSV process."""
    if not can_edit_deliveries(request.user):
        return HttpResponseForbidden(
            "You don't have permission to import scheduled deliveries."
        )

    selected_date = parse_date(request.POST.get('selected_date') or '')
    selected_date = selected_date or timezone.localdate()
    form = ScheduledDeliveryImportForm(request.POST, request.FILES)

    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect(
            f"{reverse('warehouse:dashboard')}?date={selected_date.isoformat()}"
        )

    upload = form.cleaned_data['file']
    try:
        summary = import_scheduled_delivery_file(
            upload,
            fallback_date=selected_date,
            actor=request.user,
        )
    except ScheduledDeliveryImportError as exc:
        messages.error(request, str(exc))
        return redirect(
            f"{reverse('warehouse:dashboard')}?date={selected_date.isoformat()}"
        )

    import_date = summary['scheduled_date']
    messages.success(
        request,
        (
            f'Imported {summary["processed"]} scheduled delivery row(s) for '
            f'{import_date:%b %d, %Y}: {summary["created"]} new, '
            f'{summary["updated"]} updated, {summary["unchanged"]} unchanged.'
        ),
    )
    return redirect(f"{reverse('warehouse:dashboard')}?date={import_date.isoformat()}")
