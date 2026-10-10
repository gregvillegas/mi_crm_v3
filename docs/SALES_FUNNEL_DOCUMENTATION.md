# Sales Funnel — How It Works, Deletion Behavior & Best-Practice Workflow

**Module:** `sales_funnel`
**Audience:** admins, managers (AVP/SM/ASM/Supervisor), and whoever maintains the CRM.
**Status:** As-built documentation (describes current behavior) + recommended workflow.

> **TL;DR on removing entries (current behavior):**
> - **Real entries can no longer be hard-deleted.** To take a stale real entry out of the pipeline (e.g. the customer changed requirements and a new proposal is coming), use **Remove** — a **soft delete** that requires a **reason**, records **who/when**, drops the entry from pipeline totals, and is **reviewable and restorable** (see [§3a](#3a-remove-soft-delete--restore)). A supervisor review page lists all removed entries.
> - **Only TEST entries** (`is_test=True`) can be **hard-deleted** (permanent, no undo) — for throwaway/scratch entries.
> - **Real deals still end with Close (Won/Lost)**, which preserves revenue and writes history.
> - The permanent-hard-delete behavior described in [§3](#3-what-happens-when-you-delete-a-funnel-entry) below is **historical** — it applied before Remove/soft-delete existed and now only applies to the test-entry hard delete.

---

## 1. What the Sales Funnel is

The Sales Funnel (`SalesFunnel` model, `sales_funnel/models.py`) is the pipeline tracker: one row per sales opportunity, carrying the company, requirement, cost/SRP, the owning Account Manager (salesperson), and the deal's stage and outcome.

### The four stages

| Code | Display | Color | Meaning |
|---|---|---|---|
| `quoted` | Newly Quoted | **PINK** | A quote has gone out; early pipeline. |
| `closable` | Closable Deals | **YELLOW** | Expected to close this month. |
| `project` | Green Funnel | **GREEN** | Project-based deal, **SRP ≥ ₱500,000**. |
| `services` | Blue Funnel | **BLUE** | Services deal, **SRP < ₱500,000**. |

**Auto-classification rule** (`SalesFunnel.save()`): whenever an **open** entry is in `project` or `services`, the stage is recomputed from the ₱500,000 SRP threshold — ≥ ₱500K → `project`, otherwise `services`. So you don't manually choose between Green/Blue; the amount decides. (`quoted` and `closable` are chosen manually / by workflow.)

### Status fields (how an entry's life is tracked)

- `is_active` (default **True**) — whether the entry is live pipeline.
- `is_closed` (default **False**) — set True when the deal is finished (won or lost).
- `deal_outcome` — `active` / `won` / `lost` (default `active`).
- `closed_date` — stamped automatically when `is_closed` becomes True.

The dashboard and the `visible_funnel_entries()` helper only show entries that are **`is_active=True` AND `is_closed=False`** — i.e. live pipeline. Closed (won/lost) deals drop off the board but remain in the database for reporting (see [Deals History](#deals-history--reporting)).

### Money fields

- `cost` / `retail` (SRP) are stored in PHP. `profit = retail − cost`.
- For proposal-linked entries, `display_retail` prefers the **linked proposal's** quoted PHP amount, so the funnel always reflects the live proposal value.

---

## 2. How entries are created

There are three ways an entry enters the funnel:

### (a) Manually — "Add New Entry"
`add_funnel_entry` view. Allowed roles: **salesperson, supervisor, asm, sm, avp** (not teamlead, not admin/exec). The entry is always owned by the creator (`salesperson = request.user`), starts in `quoted`, `deal_outcome=active`, with no proposal link.

### (b) Automatically from a Proposal (the main path)
When a proposal is **created, edited, approved, or sent**, `update_sales_funnel(proposal)` runs (in `sales_proposals/views.py`, also from the multi-option views and the API). It:
- Looks for an existing funnel entry **linked by the `proposal` foreign key**.
- If found → updates its `retail`, `cost` (cost is marked up ×1.05), and requirement from the proposal.
- If not found → **creates** a new `quoted` entry linked to that proposal, owned by the proposal's creator, for the proposal's customer.

> **Consequence:** a proposal and its funnel entry are kept in sync automatically. You generally should **not** hand-create a funnel entry for something that already has a proposal — let the proposal create it.

### (c) CSV import — "Import Entries"
`import_funnel_entries`. Allowed roles: salesperson, supervisor, asm, sm, avp, admin. Salespeople import to themselves; managers pick a target salesperson (validated against their team scope). Human stage names map to codes ("Newly Quoted"→quoted, "Closable This Month"→closable, "Project Based"→project, "Services"→services). A sample template is available via "Sample CSV".

---

## 3. What happens when you DELETE a funnel entry

This is the behavior you specifically asked about. Reviewed in `delete_funnel_entry` (`sales_funnel/views.py`).

### It is a permanent HARD delete
```python
entry.delete()   # real DB row removal — NOT a soft delete
```
- It does **not** set `is_active=False` or `is_closed=True`. The row is **gone from the database**.
- **No audit trail.** Unlike *closing* a deal (which writes a `CustomerHistory` record), deletion writes **no history, no audit log, and fires no signals**. There is no "deleted entries" list and **no undo**.
- **Confirmation** is only a browser `confirm()` popup ("…This action cannot be undone."). There is no server-side confirmation page.
- **Method:** only a POST actually deletes.

### Who can delete
- Decorated so almost every role can reach it (`can_access_funnel`).
- The **only** in-function guard: a **salesperson can delete only their own** entries.
- **Managers/execs (supervisor, teamlead, asm, sm, avp, admin, gm, vp) can delete ANY entry by ID** — there is **no team-scope check on delete** (unlike the dashboard list, which is scoped). The trash button is shown in the UI when the user `can_add` or `can_edit_all`.
- There is **no block on deleting a closed/won entry** — a won deal can be hard-deleted just like a pink one.

### What deletion cascades to
`SalesFunnel`'s relationships and their on-delete rules:

| Relationship | Direction | On the funnel entry's deletion |
|---|---|---|
| `salesperson` → User (`CASCADE`) | inbound | Deleting the **User** deletes all their funnel entries. (Not triggered by deleting the entry.) |
| `customer` → Customer (`CASCADE`) | inbound | Deleting the **Customer** deletes its funnel entries. (Not triggered by deleting the entry.) |
| `proposal` → Proposal (`SET_NULL`) | outbound | Deleting the entry does **nothing** to the proposal. Deleting the **proposal** just nulls the entry's link (the entry survives, falling back to its own stored `retail`). |
| `ProofOfConcept.sales_funnel` (`SET_NULL`) | reverse | Deleting the entry **nulls** the POC's link; the POC survives. |
| lead-conversion link (`SET_NULL`) | reverse | Deleting the entry **nulls** the link; the lead-conversion record survives. |

**Net:** deleting a funnel entry cascades to **nothing** downstream (both referrers use SET_NULL). It simply removes that one row.

### The two biggest risks of deleting

1. **Lost revenue in reports (silent).** Sales Monitoring, quotas, team/group achievement, and the Executive Dashboard compute won revenue/profit **live** from surviving `SalesFunnel` rows (`deal_outcome='won'` within `closed_date` windows). There is no separate ledger. **Hard-deleting a won entry permanently erases that revenue and profit from every report**, with no trace that it ever existed.

2. **Proposal-linked entries resurrect (differently).** Because auto-sync keys off the `proposal` FK, if you delete a proposal-linked entry and then anyone edits/re-saves that proposal, `update_sales_funnel` finds no linked entry and **creates a brand-new `quoted` one** — losing the stage, notes, probability, and outcome of the deleted entry, and re-cluttering the Pink funnel.

> **Bottom line (historical):** The permanent hard delete above now applies **only to TEST entries**. Real entries use **Remove** (§3a) instead, and real outcomes still use **Close (Won/Lost)**.

---

## 3a. Remove (soft delete) & Restore

This is the current way to take a **real** entry out of the pipeline. It replaces hard-deleting real entries. Implemented in `remove_funnel_entry` / `restore_funnel_entry` / `removed_funnel_entries` (`sales_funnel/views.py`).

**When to use it:** the entry is stale and shouldn't inflate the pipeline — e.g. the customer changed requirements and a fresh proposal will replace this one.

**What Remove does:**
- Requires a **reason** (a modal in the dashboard enforces it; the server also rejects an empty reason).
- Sets `is_active=False` and records `removed_reason`, `removed_at`, and `removed_by`. The row is **never destroyed**.
- The entry immediately **drops out of the dashboard and all pipeline totals** (every pipeline query already filters `is_active=True`).
- Writes a `CustomerHistory` record (`funnel_entry_removed`, amber badge) with the reason and actor, so it shows on the customer timeline.
- **Closed (won/lost) deals cannot be removed** — they're part of results history; the view blocks it.

**Review & Restore:**
- **Removed Entries** page (`sales_funnel:removed_entries`, in the Sales Funnel nav dropdown) lists removed entries with company, reason, who removed it, and when.
- **Role scoped** via the shared `funnel_scope_q(user)` helper: a salesperson sees their own; supervisor/teamlead/ASM/SM/AVP see their teams'; execs/admin see all.
- **Restore** (supervisor and above) sets `is_active=True`, clears the `removed_*` fields, and logs a `funnel_entry_restored` history record. The entry returns to the pipeline.

**Permissions:** a salesperson may Remove their **own** active entries; managers/execs may Remove any entry **within their scope** (`_can_manage_funnel_entry`). Restore is limited to supervisor-and-above.

---

## 4. The intended lifecycle (how an entry *should* move)

```
                 (proposal created)                 move / auto-reclassify
   PINK  ──────────────────────────▶  YELLOW  ──────────────────────────▶  GREEN / BLUE
 (quoted)                            (closable)                           (project/services)
   │  manual add / CSV import           │                                    │
   └───────────────────────────────────┴──────────────┬─────────────────────┘
                                                        │  Close (Won / Lost)
                                                        ▼
                                              is_closed = True
                                              deal_outcome = won | lost
                                              closed_date = today
                                              → leaves the live board,
                                                stays in Deals History & reports
```

- **Move stage:** the dashboard "move" arrows call `update_entry_stage` (AJAX, with a confirm). Moving into Green/Blue always re-derives project-vs-services from the ₱500K rule.
- **Close Won/Lost:** `close_entry` sets `is_closed`, `deal_outcome`, `closed_date`, appends a note, and — if the entry has a customer — writes a **CustomerHistory** audit record (`deal_won`/`deal_lost` with retail/cost/profit). This is the **correct, auditable** end-state for a real deal.

### Deals History & reporting
Closed deals remain queryable. "View Deals History" and the dashboards aggregate won/lost from the surviving rows. **Closing keeps the data; deleting destroys it.**

### Maintenance tools (admin/exec)
- **Normalize Stages** (`normalize_funnel_stages`, admin/president/gm/vp) — re-applies the ₱500K Green/Blue rule across open project/services entries.
- **`promote_quoted_funnel`** management command — promotes stale `quoted` entries (older than the current week) into Green/Blue by the threshold.
- **Clear Stage** (`clear_stage_entries`, admin/exec) — bulk-deletes entries by stage for a given month. ⚠️ This is also a **hard delete** of many rows — same cautions as §3, at scale.

---

## 5. Permissions at a glance

| Action | Who can do it |
|---|---|
| View board (own scope) | all funnel roles (salesperson, supervisor, teamlead, asm, sm, avp, admin, gm, vp) |
| Add entry | salesperson, supervisor, asm, sm, avp |
| Import CSV | salesperson, supervisor, asm, sm, avp, admin |
| Edit / move / close | own entries (salesperson); any visible entry (managers/execs) |
| **Delete** | salesperson (own only); **any entry** for supervisor/teamlead/asm/sm/avp/admin/gm/vp (no scope check) |
| Normalize / Clear Stage | admin, president, gm, vp |

Visibility scoping (`visible_funnel_entries`): salesperson = own; supervisor/teamlead = their groups; asm/sm = their handled groups (+ supervisors + self); avp = their teams; admin/exec = everything. All scoped to **active, open** entries only.

---

## 6. Recommended best-practice workflow

For sales staff and managers:

1. **Let proposals drive the funnel.** When there's a quote, create the **Proposal** — it auto-creates and keeps the funnel entry in sync. Only hand-add funnel entries for pipeline that has no proposal yet.
2. **Advance by moving stages**, not by recreating entries. Pink → Yellow as it becomes closable; Green/Blue is set automatically by amount.
3. **End every real deal with Close (Won/Lost)** — never Delete. Closing preserves revenue, writes customer history, and feeds quotas/dashboards. A lost deal should be closed as **Lost**, not deleted, so win-rate and history stay accurate.
4. **Delete only mistakes/duplicates** — a test entry, an obvious duplicate, or a wrong-customer entry that was never a real opportunity. Prefer doing this **before** it's ever closed/won.
5. **Never delete a WON entry** to "clean up." It erases booked revenue from reports with no trace. If a won deal was entered in error, correct it deliberately and note why (e.g. re-close as Lost, or edit the figures) rather than deleting.
6. **Managers: avoid deleting other people's entries** unless you're certain. There's no scope guard and no undo — a mis-click removes someone's pipeline permanently.

### Suggested guardrails (not yet implemented — for management sign-off)

These would reduce the risk documented in §3. Listed as options, no code changed:

- **Soft-delete / archive instead of hard delete** — a `deleted_at`/`is_deleted` flag so entries can be hidden but recovered and audited, matching how *closing* already preserves data.
- **Block deleting closed/won entries** — require they be re-opened or re-closed as Lost rather than destroyed.
- **Audit the delete** — write a `CustomerHistory` (or dedicated audit) row on delete, mirroring `close_entry`, so there's always a trace.
- **Scope manager deletes** — restrict delete to entries within the manager's own team scope (same scoping the dashboard already uses), instead of any-entry-by-ID.
- **Restrict who can delete** — e.g. limit destructive delete to admins/execs, with everyone else using Close.

If you want any of these, they're small, contained changes — tell me which and I'll implement with tests.

---

## 7. Quick field/behavior reference

- **Model:** `sales_funnel/models.py` → `SalesFunnel`.
- **Auto-sync from proposals:** `sales_proposals/views.py` → `update_sales_funnel()`.
- **Lifecycle views:** `add_funnel_entry`, `edit_funnel_entry`, `update_entry_stage`, `close_entry`, `delete_funnel_entry`, `deals_history`, `normalize_funnel_stages`, `clear_stage_entries` (all in `sales_funnel/views.py`).
- **Visibility:** `visible_funnel_entries(user)` in `sales_funnel/views.py`.
- **Won-deal reporting:** `sales_monitoring/views.py` (quota/achievement/executive dashboard) and `core/views.py` (home), all filtering `deal_outcome='won'` by `closed_date`.
- **Threshold:** ₱500,000 separates Green (project) from Blue (services).
