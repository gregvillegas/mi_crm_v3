# Warehouse App — How It Works

This document explains the `warehouse` app: the delivery itinerary board that
replaced the Excel file that used to be emailed around, the real-time
(WebSocket) updates, the **Warehouse** office role that maintains the itinerary,
the **Delivery History** report (including backlog tracing), and how Excel
export visibility works.

> Scope note: everything below reflects the code as it exists today, with file
> references so it can be re-verified.

---

## 1. Quick overview

- **What it manages:** a single `Delivery` row per S.O. / SRF# / POR#, grouped
  on screen into the three sections the warehouse used to keep in Excel —
  **For Schedule**, **Scheduled Delivery**, and **Accomplished Delivery** —
  plus a **VAN DETAILS** footer grouped by vehicle plate + driver, a paginated
  **History** page, and an **Excel export**.
- **Real-time:** every create / update / delete is pushed to every open board
  over a WebSocket (Django Channels), so a status change made by the warehouse
  office shows up instantly on the sales team's screen without a refresh.
- **Who can see it:** every internal role **except** none — the board is open to
  all roles in `DELIVERY_VIEWER_ROLES` (§7). The only role locked **out** of the
  rest of the CRM is `warehouse` (§8).
- **Who can edit it:** only the **Warehouse** role (plus `admin`).
- **Who can export it:** everyone who can view, **except** `salesperson`
  (Account Manager).

### Key files

| File | Responsibility |
|------|----------------|
| `warehouse/models.py` | `WarehouseStaff`, `Delivery`, `DeliveryQuerySet` (section + history helpers) |
| `warehouse/views.py` | Dashboard, history, create/update, Excel export, role helpers |
| `warehouse/forms.py` | `DeliveryForm` (add/edit) |
| `warehouse/urls.py` | Routes under `/warehouse/` |
| `warehouse/admin.py` | `WarehouseStaffAdmin`, `DeliveryAdmin` (inline status/driver/plate editing) |
| `warehouse/consumers.py` | `DeliveryFeedConsumer` + `broadcast_delivery_event()` |
| `warehouse/routing.py` | WebSocket route `ws/warehouse/deliveries/` |
| `warehouse/signals.py` | `post_save` / `post_delete` → broadcast |
| `warehouse/apps.py` | Registers the signals on app ready |
| `warehouse/management/commands/import_warehouse_itinerary.py` | One-off Excel import of the legacy itinerary |
| `warehouse/templates/warehouse/` | `delivery_dashboard.html`, `delivery_history.html`, `delivery_form.html`, `_delivery_row.html` |
| `crm_project/asgi.py`, `crm_project/settings.py` | ASGI router + `CHANNEL_LAYERS` wiring |

---

## 2. Data model (`warehouse/models.py`)

### `WarehouseStaff`

A **lookup list only — no login**. Drivers and helpers never sign in; they only
need to appear in the "Warehouse Staff" dropdown and in the history report.

- `name` — unique.
- `is_active` — uncheck to hide a name from the dropdown **without losing
  history** (past deliveries keep their link).

Managed in Django admin (`WarehouseStaffAdmin` has `is_active` as an inline
editable column).

### `Delivery`

Mirrors the columns of the legacy Excel itinerary:

- **Identity:** `so_number` (unique, "S.O. / SRF# / POR#"), `client`, `item`,
  `area`.
- **Logistics:** `driver_staff`, `vehicle_plate`,
  `warehouse_staff` (FK → `WarehouseStaff`, `on_delete=SET_NULL`).
- **Sales:** `ae` (Account Executive initials, e.g. `CSV`, `MGA`), `remarks`.
- **Workflow:** `status`, `scheduled_date`, `accomplished_date`, `updated_at`.
- **Backlog tracing:** `is_backlog` (bool), `backlog_count` (int) — see §6.

`save()` automatically:

1. Stamps `scheduled_date` (= today) the first time a row becomes **Scheduled**.
2. Stamps `accomplished_date` (= today) the first time a row becomes
   **Accomplished**.
3. Flags **backlog**: when a row is moved *back* from Scheduled/Accomplished to
   For Schedule, `is_backlog` is set to `True` and `backlog_count` is
   incremented.

`to_dict()` returns the JSON payload used by the WebSocket feed.

### `DeliveryQuerySet` helpers

| Method | Returns |
|--------|---------|
| `for_schedule()` | Section 1 — all `FOR_SCHEDULE` rows |
| `scheduled_on(day)` | Section 2 — `SCHEDULED` rows for `day` |
| `accomplished_on(day)` | Section 3 — `ACCOMPLISHED` rows for `day` |
| `delivery_history()` | All rows **except** plain `FOR_SCHEDULE` items that were never scheduled — i.e. everything Scheduled/Accomplished **plus** backlog items |

---

## 3. The delivery board (`warehouse/views.py` → `delivery_dashboard`)

Three stacked cards, each with a **date picker** in its header:

1. **FOR SCHEDULE** — new / pending / failed items. Remarks render in
   **bold red** for emphasis.
2. **SCHEDULED DELIVERY** — items for the selected day, grouped by vehicle plate
   then S.O.; the header date picker reloads the board for that day.
3. **ACCOMPLISHED DELIVERY** — items completed the previous day; its date picker
   shifts the whole board (it sets `?date=` to the picked day **+ 1**).

Below the Scheduled card sits the **VAN DETAILS** footer, produced by
`_build_van_details()`: rows grouped by `(vehicle_plate, driver_staff)` with an
item **count** (the "SO NUMBERS" column was intentionally removed).

- `?date=YYYY-MM-DD` selects the day (defaults to today).
- The board is wrapped in `#delivery-board` with `data-can-edit`, which the inline
  JavaScript uses to decide whether to build an **ACTION** column.

---

## 4. Add / update from the app (`DeliveryForm`)

The **Warehouse** role (and `admin`) gets a **New Delivery** button in the board
header and a per-row **edit** (pencil) link:

- `warehouse:create` → `DeliveryForm` (`page_title="New Delivery"`).
- `warehouse:update` (`<pk>/edit/`) → same form bound to the instance.

`DeliveryForm` covers `so_number, client, item, area, driver_staff,
vehicle_plate, warehouse_staff, ae, remarks, status, scheduled_date,
accomplished_date`. The `warehouse_staff` dropdown lists **active** names only,
but a delivery already pointing at a since-deactivated name keeps working (the
deactivated row stays in the queryset for that instance).

The **Delivery Admin** also offers inline editing of `status`, `driver_staff`,
`vehicle_plate`, and `warehouse_staff` straight from the change list.

---

## 5. Real-time updates (Django Channels)

```
warehouse/models.py  ──post_save / post_delete──▶  warehouse/signals.py
      │                                                   │
      │                                     broadcast_delivery_event()
      │                                                   ▼
      │                              channel_layer.group_send('warehouse_deliveries',
      │                                       {'type':'delivery.event','payload':…})
      ▼                                                   │
   (any save)                                 DeliveryFeedConsumer.delivery_event()
                                                          ▼
                                            browser JS moves the row between
                                            the three sections — no reload
```

- **Consumer:** `DeliveryFeedConsumer` (`AsyncWebsocketConsumer`). Anonymous
  sockets are refused with close code **4401**.
- **Group:** a single global group `warehouse_deliveries` shared by all boards.
- **Routing:** `ws/warehouse/deliveries/` (`warehouse/routing.py`), mounted in
  `crm_project/asgi.py` behind `AuthMiddlewareStack`.
- **Channel layer:** Redis when `REDIS_URL` is set, otherwise the in-memory layer
  (single-process dev only). A failed broadcast is logged and swallowed so it can
  never break the save that triggered it.
- `daphne` is listed first in `INSTALLED_APPS` so `runserver` serves ASGI in dev.

---

## 6. Backlog tracing

When an item that was already **Scheduled** (or **Accomplished**) is moved back
to **For Schedule**, the system records it as a **backlog** item:

- `is_backlog = True`, and `backlog_count` increments on every move back.
- The board shows a red **BACKLOG** badge next to the S.O. number; hovering it
  reveals how many times the item was moved back.
- Backlog rows are **kept in `delivery_history()`**, so they appear on the
  History page even though they are not yet completed.

This gives management a durable record for **driver/staff KPI**, recurring
delays, and general delivery-process improvement.

---

## 7. History page (`delivery_history`)

`/warehouse/history/` lists everything from `Delivery.objects.delivery_history()`
— **Scheduled, Accomplished, and backlog rows** — paginated at
`HISTORY_PAGE_SIZE = 50`.

Columns: **DATE · STATUS · COMPANY · ITEM · AE · DRIVER · WAREHOUSE STAFF**.

- STATUS shows `Accomplished` (green), `Scheduled` (yellow), or `Backlog` (red);
  a secondary **BACKLOG** badge marks rows that were previously moved back.
- DATE shows `accomplished_date` for done items, otherwise `scheduled_date`.

---

## 8. Roles, access, and the soft lock

Role sets live at the top of `warehouse/views.py`:

| Constant | Members | Meaning |
|----------|---------|---------|
| `DELIVERY_VIEWER_ROLES` | `salesperson, avp, supervisor, teamlead, asm, admin, president, gm, vp, technical_sales, techmgr, asst_techmgr, warehouse` | May open the board & history |
| `DELIVERY_EDITOR_ROLES` | `warehouse, admin` | May add / update deliveries |
| `DELIVERY_EXPORT_EXCLUDED_ROLES` | `salesperson` | May view but **not** export |

**Export visibility:** `can_export_deliveries(user)` = can-view **and not** in
`DELIVERY_EXPORT_EXCLUDED_ROLES` — i.e. the Excel export is visible to **all
viewers except the Account Manager (salesperson)** role.

### The `warehouse` role is soft-locked to this app

The `warehouse` role exists to maintain the itinerary and should see nothing
else. The lock is **soft** (no middleware): the navbar and the home page simply
hide / redirect, and the "see everything" default fall-throughs in other apps
return **403**.

- **Navbar / mobile tab bar** (`templates/base.html`): for `user.role ==
  'warehouse'` only two links render — **Warehouse Deliveries** and **Delivery
  History**; the global search and all other modules are hidden.
- **Home** (`core/views.py`): `warehouse` users are redirected straight to
  `warehouse:dashboard`.
- **403 guards** close the permissive defaults in `sales_monitoring/views.py`,
  `sales_proposals/views.py`, and `sales_funnel/views.py`.

Every other role keeps the normal "Warehouse Deliveries" entry under the
**Monitoring** dropdown.

---

## 9. Excel export (`export_deliveries_excel`)

`/warehouse/export/` builds a workbook (openpyxl) with **one sheet per section**,
preserving the Excel the buyers used offline:

- Sheets: `FOR SCHEDULE`, `SCHEDULED DELIVERY`, `ACCOMPLISHED DELIVERY`, each
  colour-coded, frozen header row, and column widths matching the board.
- `FOR_SCHEDULE` remarks keep the bold-red emphasis.
- A **VAN DETAILS** footer (plate / driver / items) is appended under the
  Scheduled sheet.
- Ordered and column-defined by the shared `DELIVERY_COLUMNS` constant so the
  export can never drift from the board.

Access is gated by `can_export_deliveries()` (403 for `salesperson`).

---

## 10. Legacy Excel import

`manage.py import_warehouse_itinerary` reads
`WHSE ITINERARY-OCTOBER 30  2026.xlsx` from the project root and populates the
board from its three sheets (`FOR SCHEDULE`, `ACCOMPLISHED`, `SCHEDULED
DELIVERY `):

- `update_or_create` on `so_number` keeps it safe to re-run.
- Blank rows are skipped and the loop stops at the `VAN DETAILS` footer.
- Combined names such as `ROMMEL-BENJIE` are **split** — `ROMMEL` becomes the
  `driver_staff` and `BENJIE` is created/fetched as a `WarehouseStaff` row
  (`GERRY-MARLON` → driver `GERRY`, staff `MARLON`).

> The source workbook is a one-off seed. Once imported, the board is the source
> of truth.

---

## 11. Tests

`warehouse/tests.py` covers the model helpers, the dashboard view, the role
rules, and the soft lock:

- **Model:** status date stamping, section querysets, backlog flagging.
- **Board:** viewer access, remarks emphasis, van grouping.
- **Roles:** `warehouse` can create/update and sees the controls; non-editors
  are 403 on create/update; export blocked for `salesperson`; export allowed for
  `warehouse`.
- **History:** content and pagination.
- **Soft lock:** home redirects `warehouse` to the board; sales monitoring and
  proposal list are 403; the navbar hides other modules.

Run them with:

```bash
./venv/bin/python manage.py test warehouse
```
