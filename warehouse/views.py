from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import Delivery

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
}


def _can_view_deliveries(user):
    return getattr(user, 'role', None) in DELIVERY_VIEWER_ROLES


def _selected_date(request):
    """Return the ?date=YYYY-MM-DD value, defaulting to today."""
    parsed = parse_date(request.GET.get('date') or '')
    return parsed or timezone.localdate()


def _build_van_details(deliveries):
    """
    Group the scheduled deliveries by (vehicle plate, driver) to generate the
    VAN DETAILS footer under the "Scheduled Delivery" table.
    """
    grouped = {}
    for delivery in deliveries:
        plate = (delivery.vehicle_plate or '').strip()
        driver = (delivery.driver_staff or '').strip()
        if not plate and not driver:
            continue
        grouped.setdefault((plate, driver), []).append(delivery.so_number)

    return [
        {
            'vehicle_plate': plate,
            'driver_staff': driver,
            'count': len(so_numbers),
            'so_numbers': so_numbers,
        }
        for (plate, driver), so_numbers in grouped.items()
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
    }
    return render(request, 'warehouse/delivery_dashboard.html', context)


@login_required
def export_deliveries_excel(request):
    """
    Excel fallback: download the current dashboard as a workbook with one sheet
    per section, so offline users get the same itinerary they used to receive
    by email.
    """
    if not _can_view_deliveries(request.user):
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
