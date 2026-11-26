# Purchasing App — Feature Plan

**Status:** Pending Management Approval
**Date:** November 2026
**Priority:** New Module
**Estimated Effort:** Phase 1: 4–6 days | Phase 2: 6–8 days | Phase 3: 4–6 days

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Business Context & Goals](#2-business-context--goals)
3. [Current State — Gaps](#3-current-state--gaps)
4. [Guiding Principles](#4-guiding-principles)
5. [Proposed Phases](#5-proposed-phases)
6. [Data Model Design](#6-data-model-design)
7. [Role & Access Matrix](#7-role--access-matrix)
8. [User Interface Plan](#8-user-interface-plan)
9. [Integration with Existing Modules](#9-integration-with-existing-modules)
10. [Implementation Steps (phase by phase)](#10-implementation-steps-phase-by-phase)
11. [Files to Create / Modify](#11-files-to-create--modify)
12. [Risks & Decisions Required](#12-risks--decisions-required)
13. [Acceptance Criteria per Phase](#13-acceptance-criteria-per-phase)

---

## 1. Executive Summary

Build a new **Purchasing** module with a phased rollout:

- **Phase 1 (now):** Supplier master list + supplier price lists (buying prices, lead times, validity) — gives procurement a single reference for what to pay and when goods arrive.
- **Phase 2:** Purchase Orders + supplier incoming-delivery / ETA tracking with status timeline and delay alerts.
- **Phase 3 (optional / future):** Stock-on-hand, receiving, and integration with the proposed Sales Order app so POs are generated from approved SO line items.

This plan covers **Phases 1–3** at a design level. Only **Phase 1** is scoped for implementation now.

---

## 2. Business Context & Goals

Today procurement work happens outside the CRM:
- Supplier contact details live in spreadsheets / email.
- Buying prices and lead times are not centrally recorded — salespeople guess costs when building proposals.
- Incoming supplier deliveries and ETAs are tracked manually.

The Purchasing app closes these gaps starting with the **price list**, because that is the highest-value, lowest-risk first deliverable.

---

## 3. Current State — Gaps

| Need | Current state |
|---|---|
| Supplier master data | **None.** No `Supplier` model anywhere in the codebase. |
| Product catalog | **None.** Products exist only as free-text `ProposalItem` rows (`part_number`, `description`, `unit_cost`). No canonical product master. |
| Buying prices | **None.** `ProposalItem.unit_cost` is entered ad hoc per proposal. No supplier-specific price, validity, or lead time. |
| ETA / incoming delivery tracking | **None.** `warehouse.Delivery` is the *outbound* (customer delivery) flow; there is no inbound (supplier) delivery model. |
| Purchasing user role | **None.** `ROLE_CHOICES` has no purchasing role. (`SALES_ORDER_PLAN.md` references a `purchasing_supervisor` role for the SO approval chain, but it does not exist yet.) |

---

## 4. Guiding Principles

1. **Build a Product catalog first.** Supplier prices attach to a canonical `Product`, not to free-text descriptions. This prevents drift and enables future ProposalItem auto-fill and inventory.
2. **Audit trail for every price change.** Reuse the project's established event-log pattern (`DeliveryEvent`, `CustomerHistory`, `TeamMembershipQuotaLog`) — a `SupplierPriceLog` row on every create/edit.
3. **No cross-app side effects in Phase 1.** Adding the app and its data must not change sales, funnel, warehouse, or customer behavior. Integration is deferred.
4. **Extensible to ETA tracking.** The `Product` + `SupplierPrice` model is designed so Phase 2's `PurchaseOrderItem` can reference `SupplierPrice` directly.
5. **Role-based access follows existing conventions.** New `purchasing` / `purchasing_supervisor` roles; admin always full access; executives read-only.

---

## 5. Proposed Phases

### Phase 1 — Supplier & Price List Management (this implementation)
- Supplier master (CRUD, active/inactive)
- Product catalog (CRUD, categories, UOM)
- Supplier price list: per supplier + product, with unit cost, currency, lead time (days), validity window, active flag, notes
- Price change audit log
- Dashboard: supplier list, supplier detail with price table, search/filter by supplier, product, category, currency, validity

### Phase 2 — Purchase Orders & ETA Tracking
- Purchase Order (PO) header + line items referencing `SupplierPrice`
- PO status lifecycle: Draft → Sent → Confirmed → In Transit → Delivered / Partial / Cancelled
- ETA tracking: expected delivery date, actual delivery date, delay flag, notes
- PO event timeline (`POEvent`, mirroring `DeliveryEvent`)
- Dashboard: upcoming ETAs, delayed shipments, open POs
- Optional: WebSocket live updates (mirror warehouse `consumers.py`)

### Phase 3 — Inventory & Sales Order Integration (future)
- Stock-on-hand per product/location
- Receiving against PO (GRN)
- Auto-generate PO line items from an approved Sales Order (when the SO app is built)
- Cost-variance reporting (quoted vs actual buy price)

---

## 6. Data Model Design

### Phase 1 Models

#### `Supplier`
```python
class Supplier(models.Model):
    name = models.CharField(max_length=200, unique=True)
    contact_person = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    payment_terms = models.CharField(max_length=100, blank=True, help_text="e.g. Net 30, 50% down")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

#### `ProductCategory` (lookup)
```python
class ProductCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
```

#### `Product` (catalog master)
```python
class Product(models.Model):
    sku = models.CharField(max_length=100, unique=True, help_text="Internal part number / SKU")
    description = models.TextField()
    category = models.ForeignKey(ProductCategory, on_delete=models.SET_NULL, null=True, blank=True)
    default_uom = models.CharField(max_length=30, default='unit', help_text="e.g. unit, box, meter")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

#### `SupplierPrice` (the price list entry)
```python
class SupplierPrice(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='prices')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='supplier_prices')
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default='PHP')
    lead_time_days = models.PositiveIntegerField(null=True, blank=True, help_text="Typical delivery lead time from this supplier")
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('supplier', 'product')  # one active price per supplier+product
        ordering = ['supplier__name', 'product__sku']
```

#### `SupplierPriceLog` (audit trail)
```python
class SupplierPriceLog(models.Model):
    price = models.ForeignKey(SupplierPrice, on_delete=models.CASCADE, related_name='logs')
    previous_unit_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    new_unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    previous_lead_time_days = models.PositiveIntegerField(null=True)
    new_lead_time_days = models.PositiveIntegerField(null=True)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
```

### Phase 2 Models (design only)
- `PurchaseOrder` (supplier, status, po_number, order_date, expected_delivery_date, actual_delivery_date, total_amount, created_by)
- `PurchaseOrderItem` (po FK, product FK, supplier_price FK, quantity, unit_cost, line_total)
- `POEvent` (status transitions, remarks, actor, timestamp) — mirrors `DeliveryEvent`

### Phase 3 Models (design only)
- `StockMovement` (product, qty_in/out, reference PO/SO, location, date)
- `GoodsReceipt` / receiving against PO

---

## 7. Role & Access Matrix

Phase 1 requires **two new roles** (mirroring the `purchasing_supervisor` role already named in `SALES_ORDER_PLAN.md`):

| Role | Access |
|---|---|
| `admin` | Full CRUD on Supplier, Product, SupplierPrice; view logs |
| `purchasing_supervisor` | Full CRUD on Supplier, Product, SupplierPrice; view logs |
| `purchasing` | View all; create/edit Supplier and SupplierPrice; cannot delete |
| `gm`, `vp`, `president`, `avp` | Read-only dashboard + price list (executive visibility) |
| `salesperson`, `supervisor`, `sm`, `asm`, `technical_sales`, etc. | No access (Phase 1) — Proposal cost remains manual |

> **Decision needed:** Confirm whether `purchasing` and `purchasing_supervisor` are the final role names, and whether executives should see buying costs (cost visibility is sensitive).

---

## 8. User Interface Plan

### Phase 1 Screens

1. **Purchasing Dashboard** (`/purchasing/`)
   - Summary cards: Total Suppliers, Active Products, Active Prices, Expiring Prices (next 30 days)
   - Supplier list table (search, filter by active status)

2. **Supplier Detail** (`/purchasing/suppliers/<id>/`)
   - Supplier info (editable)
   - Price list table: product SKU, description, unit cost, currency, lead time, validity, actions (edit / deactivate / view history)
   - "Add Price" button

3. **Product Catalog** (`/purchasing/products/`)
   - CRUD table: SKU, description, category, UOM, active
   - Search/filter by category, active

4. **Product Detail / Supplier Prices**
   - Product info
   - Table of all suppliers that carry this product with their current price + lead time (useful for price comparison)

5. **Price Change History** (modal or inline on supplier detail)
   - Per `SupplierPrice`: date, previous cost → new cost, changed by, notes

6. **Forms** (crispy_forms, Bootstrap 5)
   - SupplierForm, ProductForm, ProductCategoryForm, SupplierPriceForm

### Conventions
- Compact, single-line table rows with `title` hover tooltips (per user preference)
- Explicit Save/Cancel buttons (no Enter-to-submit dependency)
- Natural-width action buttons
- DataTables for long lists with search/filter

---

## 9. Integration with Existing Modules

| Module | Phase 1 | Phase 2 | Phase 3 |
|---|---|---|---|
| **Sales Proposals** | No change. `ProposalItem.unit_cost` stays manual. | No change. | Optional: auto-fill `unit_cost` from the product's preferred supplier price. |
| **Sales Funnel** | No change. | No change. | No direct link. |
| **Warehouse** | No change. | No change. | Receiving updates stock; outbound `Delivery` consumes stock. |
| **Sales Order (planned)** | No change. | No change. | Approved SO line items auto-create PO drafts. |
| **Users** | Add `purchasing`, `purchasing_supervisor` to `ROLE_CHOICES`. | — | — |
| **teams / scoping** | Purchasing is company-wide (not team-scoped). No `TeamMembership` needed. | — | — |

---

## 10. Implementation Steps (phase by phase)

### Phase 1 — Supplier & Price List Management

1. Create `purchasing` app: `python manage.py startapp purchasing`
2. Add `'purchasing'` to `INSTALLED_APPS` in `crm_project/settings.py`
3. Add `purchasing` and `purchasing_supervisor` to `User.ROLE_CHOICES` in `users/models.py`
4. Create models: `ProductCategory`, `Product`, `Supplier`, `SupplierPrice`, `SupplierPriceLog`
5. Run `makemigrations purchasing` + `migrate`
6. Register models in `purchasing/admin.py`
7. Create forms: `SupplierForm`, `ProductForm`, `ProductCategoryForm`, `SupplierPriceForm`
8. Create views:
   - `purchasing_dashboard` (cards + supplier list)
   - `supplier_list`, `supplier_create`, `supplier_update`, `supplier_detail`
   - `product_list`, `product_create`, `product_update`
   - `supplier_price_create`, `supplier_price_update` (inline on supplier detail)
   - `supplier_price_history` (modal/list)
9. Add audit logging: write a `SupplierPriceLog` row inside `supplier_price_create` / `supplier_price_update` (capture `previous_*` before save)
10. Create `purchasing/urls.py` + include in project `urls.py`
11. Create templates (Bootstrap 5, crispy, DataTables):
    - `purchasing/dashboard.html`
    - `purchasing/supplier_list.html`, `supplier_form.html`, `supplier_detail.html`
    - `purchasing/product_list.html`, `product_form.html`
    - `purchasing/supplier_price_form.html`, `supplier_price_history.html`
12. Add nav link in the base template navbar (visible to `admin`, `purchasing`, `purchasing_supervisor`; read-only link for execs)
13. Add role decorator / mixin for purchasing access (`admin` + purchasing roles)
14. Write tests: supplier CRUD, price CRUD, price log on change, role access, product uniqueness
15. Run `python manage.py test purchasing` and `python manage.py check`

### Phase 2 — Purchase Orders & ETA Tracking

1. Add models: `PurchaseOrder` (status lifecycle), `PurchaseOrderItem`, `POEvent`
2. Migrations
3. PO numbering convention (e.g. `PO-YYYY-0001`)
4. PO CRUD views + templates (draft → send → confirm → in transit → delivered)
5. ETA dashboard: upcoming ETAs, delayed shipments (expected < today and not delivered)
6. `POEvent` audit on every status change (mirror `DeliveryEvent` signal approach in `warehouse/signals.py`)
7. PO detail with status timeline
8. (Optional) WebSocket consumer for live ETA updates
9. Tests: PO lifecycle, ETA delay detection, event logging

### Phase 3 — Inventory & SO Integration

1. `StockMovement` model
2. Receiving against PO (GRN)
3. Stock-on-hand dashboard
4. Integration hook with Sales Order line items → PO draft generation
5. Cost-variance report (quoted `ProposalItem.unit_cost` vs actual `PurchaseOrderItem.unit_cost`)

---

## 11. Files to Create / Modify

### Create (Phase 1)
- `purchasing/__init__.py`, `apps.py`, `admin.py`, `models.py`, `forms.py`, `views.py`, `urls.py`, `tests.py`
- `purchasing/migrations/0001_initial.py`
- `purchasing/templates/purchasing/*.html` (6–7 templates)

### Modify (Phase 1)
- `crm_project/settings.py` — add `'purchasing'` to `INSTALLED_APPS`
- `users/models.py` — add `purchasing`, `purchasing_supervisor` to `ROLE_CHOICES`
- `crm_project/urls.py` — include `purchasing.urls`
- `templates/base.html` (or navbar partial) — add Purchasing nav link with role visibility

---

## 12. Risks & Decisions Required

| # | Decision | Default recommendation |
|---|---|---|
| 1 | New role names | `purchasing`, `purchasing_supervisor` (matches `SALES_ORDER_PLAN.md`) |
| 2 | Should executives see buying costs? | Read-only dashboard for `gm/vp/president/avp` — confirm with management since costs are sensitive |
| 3 | Should salespeople see supplier prices? | **No** in Phase 1 (cost opacity). Revisit in Phase 3 for Proposal auto-fill. |
| 4 | Currency handling | Multi-currency on `SupplierPrice.unit_cost` with a `currency` field (default PHP) |
| 5 | One price per supplier+product, or multiple (history kept as rows)? | One active row per supplier+product (`unique_together`); history in `SupplierPriceLog`. Simpler and matches `TeamMembershipQuotaLog`. |
| 6 | Product SKU uniqueness | Unique on `sku`; enforce at DB level. |

---

## 13. Acceptance Criteria per Phase

### Phase 1
- [ ] Admin can create/edit/deactivate suppliers
- [ ] Admin can create/edit products (with category, UOM)
- [ ] Admin can add a supplier price (supplier + product + cost + currency + lead time + validity)
- [ ] Editing a price creates a `SupplierPriceLog` row (previous cost, new cost, who, when)
- [ ] Supplier detail page shows the full price list for that supplier
- [ ] Product detail page shows all suppliers carrying that product (price comparison)
- [ ] Users without purchasing roles cannot access purchasing URLs (403 or redirect)
- [ ] Purchasing role users can view all and create/edit (no delete)
- [ ] Executives see a read-only dashboard
- [ ] All tests pass; `python manage.py check` clean

### Phase 2
- [ ] PO can be created from supplier prices
- [ ] PO status transitions are logged in `POEvent`
- [ ] ETA dashboard flags delayed shipments
- [ ] PO detail shows full status timeline

### Phase 3
- [ ] Stock-on-hand updated on receiving
- [ ] PO can be generated from approved Sales Order line items

---

## Next Step

Await management approval on:
1. Phase 1 scope (Supplier + Product catalog + Supplier price list + audit log)
2. New role names (`purchasing`, `purchasing_supervisor`)
3. Executive cost-visibility decision

Once approved, proceed with the Phase 1 implementation steps in §10.
