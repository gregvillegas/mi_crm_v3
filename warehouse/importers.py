import csv
import io
import os
import re
from datetime import date, datetime

import openpyxl
from django.utils import timezone

from .models import Delivery, WarehouseStaff


class ScheduledDeliveryImportError(Exception):
    """Raised when an uploaded scheduled-delivery file cannot be parsed."""


def import_scheduled_delivery_file(uploaded_file, fallback_date=None, actor=None):
    """
    Import scheduled deliveries from either:
    - an Excel workbook containing the "SCHEDULED DELIVERY" sheet, or
    - a CSV file with matching column headers.

    Existing deliveries are updated in place by `so_number`; rows not present in
    the upload are left untouched so the in-progress rollout stays conservative.
    """

    file_name = getattr(uploaded_file, 'name', '') or 'upload'
    extension = os.path.splitext(file_name)[1].lower()
    fallback_date = fallback_date or timezone.localdate()

    if extension in {'.xlsx', '.xlsm'}:
        parsed = _parse_scheduled_excel(uploaded_file)
    elif extension == '.csv':
        parsed = _parse_scheduled_csv(uploaded_file, fallback_date=fallback_date)
    else:
        raise ScheduledDeliveryImportError(
            'Unsupported file type. Please upload an .xlsx, .xlsm, or .csv file.'
        )

    rows = parsed['rows']
    if not rows:
        raise ScheduledDeliveryImportError(
            'No scheduled delivery rows were found in the uploaded file.'
        )

    imported_dates = {
        row['fields'].get('scheduled_date')
        for row in rows
        if row['fields'].get('scheduled_date')
    }
    effective_date = (
        imported_dates.pop()
        if len(imported_dates) == 1
        else parsed.get('scheduled_date') or fallback_date
    )

    summary = _upsert_scheduled_rows(rows, actor=actor, source_name=file_name)
    summary['scheduled_date'] = effective_date
    return summary


def _clean_value(value):
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%m-%d-%Y', '%b %d, %Y', '%B %d, %Y'):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
    return None


def _normalize_sheet_name(name):
    return re.sub(r'[^A-Z0-9]+', ' ', (name or '').upper()).strip()


def _normalize_driver_staff_key(value):
    return re.sub(r'[^A-Z0-9]+', '-', _clean_value(value).upper()).strip('-')


def _split_driver_staff(raw_value):
    raw_value = _clean_value(raw_value)
    if not raw_value:
        return '', None

    parts = [part.strip() for part in re.split(r'\s*[-/]\s*', raw_value, maxsplit=1)]
    driver_name = parts[0]
    warehouse_staff = None
    if len(parts) > 1 and parts[1]:
        warehouse_staff, _ = WarehouseStaff.objects.get_or_create(name=parts[1])
    return driver_name, warehouse_staff


def _find_scheduled_sheet(workbook):
    target = 'SCHEDULED DELIVERY'
    for sheet_name in workbook.sheetnames:
        if _normalize_sheet_name(sheet_name) == target:
            return workbook[sheet_name]
    raise ScheduledDeliveryImportError(
        'The workbook does not contain a "SCHEDULED DELIVERY" sheet.'
    )


def _parse_scheduled_excel(uploaded_file):
    uploaded_file.seek(0)
    try:
        workbook = openpyxl.load_workbook(uploaded_file, data_only=True)
    except Exception as exc:
        raise ScheduledDeliveryImportError(
            'Could not read the Excel file. Please upload a valid workbook.'
        ) from exc

    worksheet = _find_scheduled_sheet(workbook)
    scheduled_date = _parse_date(worksheet.cell(row=3, column=3).value)

    raw_rows = []
    van_map = {}
    in_van_section = False
    empty_streak = 0

    for row in worksheet.iter_rows(min_row=5, max_col=7, values_only=True):
        first_cell = _clean_value(row[0] if row else '')
        row_values = [_clean_value(value) for value in row]
        if not any(row_values):
            empty_streak += 1
            if empty_streak >= 25:
                break
            continue

        empty_streak = 0
        if first_cell.upper() == 'VAN DETAILS':
            in_van_section = True
            continue

        if in_van_section:
            if ' - ' in first_cell:
                plate, driver_staff = first_cell.split(' - ', 1)
                van_map[_normalize_driver_staff_key(driver_staff)] = plate.strip()
            continue

        raw_rows.append(
            {
                'so_number': first_cell,
                'client': row_values[1] if len(row_values) > 1 else '',
                'item': row_values[2] if len(row_values) > 2 else '',
                'area': row_values[3] if len(row_values) > 3 else '',
                'driver_staff_raw': row_values[4] if len(row_values) > 4 else '',
                'ae': row_values[5] if len(row_values) > 5 else '',
                'remarks': row_values[6] if len(row_values) > 6 else '',
            }
        )

    rows = []
    for raw_row in raw_rows:
        if not raw_row['so_number']:
            continue
        driver_name, warehouse_staff = _split_driver_staff(raw_row['driver_staff_raw'])
        fields = {
            'client': raw_row['client'],
            'item': raw_row['item'],
            'area': raw_row['area'],
            'driver_staff': driver_name,
            'warehouse_staff': warehouse_staff,
            'vehicle_plate': van_map.get(
                _normalize_driver_staff_key(raw_row['driver_staff_raw']),
                '',
            ),
            'ae': raw_row['ae'],
            'remarks': raw_row['remarks'],
            'status': Delivery.STATUS_SCHEDULED,
            'scheduled_date': scheduled_date or timezone.localdate(),
            'accomplished_date': None,
        }
        rows.append({'so_number': raw_row['so_number'], 'fields': fields})

    return {
        'rows': rows,
        'scheduled_date': scheduled_date,
    }


def _normalized_csv_headers(fieldnames):
    headers = {}
    for fieldname in fieldnames or []:
        headers[re.sub(r'[^a-z0-9]+', '', (fieldname or '').lower())] = fieldname
    return headers


def _require_csv_header(headers, options, label):
    for option in options:
        if option in headers:
            return headers[option]
    raise ScheduledDeliveryImportError(
        f'CSV is missing the required "{label}" column.'
    )


def _optional_csv_header(headers, options):
    for option in options:
        if option in headers:
            return headers[option]
    return None


def _parse_scheduled_csv(uploaded_file, fallback_date):
    uploaded_file.seek(0)
    try:
        decoded = uploaded_file.read().decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ScheduledDeliveryImportError(
            'Could not read the CSV file. Please save it as UTF-8 CSV.'
        ) from exc

    reader = csv.DictReader(io.StringIO(decoded))
    headers = _normalized_csv_headers(reader.fieldnames)
    so_header = _require_csv_header(
        headers,
        {'so', 'sonumber', 'sosrfpor', 'sosrfpor'},
        'S.O. / SRF# / POR#',
    )
    client_header = _require_csv_header(headers, {'client'}, 'CLIENT')
    item_header = _require_csv_header(headers, {'item', 'itemparticular'}, 'ITEM')
    area_header = _optional_csv_header(headers, {'area'})
    driver_header = _optional_csv_header(headers, {'driverstaff', 'driver'})
    plate_header = _optional_csv_header(headers, {'vehicleplate', 'plate'})
    ae_header = _optional_csv_header(headers, {'ae'})
    remarks_header = _optional_csv_header(headers, {'remarks', 'remark'})
    scheduled_date_header = _optional_csv_header(
        headers,
        {'scheduleddate', 'date'},
    )

    rows = []
    resolved_date = None

    for csv_row in reader:
        so_number = _clean_value(csv_row.get(so_header))
        if not so_number:
            continue

        driver_name, warehouse_staff = _split_driver_staff(csv_row.get(driver_header, ''))
        row_date = _parse_date(csv_row.get(scheduled_date_header, '')) or fallback_date
        if resolved_date is None:
            resolved_date = row_date

        fields = {
            'client': _clean_value(csv_row.get(client_header)),
            'item': _clean_value(csv_row.get(item_header)),
            'area': _clean_value(csv_row.get(area_header, '')),
            'driver_staff': driver_name,
            'warehouse_staff': warehouse_staff,
            'ae': _clean_value(csv_row.get(ae_header, '')),
            'remarks': _clean_value(csv_row.get(remarks_header, '')),
            'status': Delivery.STATUS_SCHEDULED,
            'scheduled_date': row_date,
            'accomplished_date': None,
        }
        if plate_header:
            fields['vehicle_plate'] = _clean_value(csv_row.get(plate_header, ''))

        rows.append({'so_number': so_number, 'fields': fields})

    return {
        'rows': rows,
        'scheduled_date': resolved_date or fallback_date,
    }


def _delivery_has_changes(delivery, fields):
    for field_name, new_value in fields.items():
        current_value = getattr(delivery, field_name)
        if field_name == 'warehouse_staff':
            current_value = delivery.warehouse_staff_id
            new_value = new_value.pk if new_value else None
        if current_value != new_value:
            return True
    return False


def _upsert_scheduled_rows(rows, actor, source_name):
    created_count = 0
    updated_count = 0
    unchanged_count = 0

    for row in rows:
        delivery = Delivery.objects.filter(so_number=row['so_number']).first()
        is_new = delivery is None
        if is_new:
            delivery = Delivery(so_number=row['so_number'])

        changed = is_new or _delivery_has_changes(delivery, row['fields'])
        for field_name, value in row['fields'].items():
            setattr(delivery, field_name, value)

        delivery._event_user = actor
        delivery._event_note = (
            f'Imported from scheduled delivery file "{source_name}".'
        )
        delivery.save()

        if is_new:
            created_count += 1
        elif changed:
            updated_count += 1
        else:
            unchanged_count += 1

    return {
        'processed': len(rows),
        'created': created_count,
        'updated': updated_count,
        'unchanged': unchanged_count,
    }
