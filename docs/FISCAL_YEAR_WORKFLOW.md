# Fiscal-Year Performance Workflow (FY Summary & Year-over-Year Comparison)

**Audience:** GM/VP, AVPs, admins, and whoever maintains the CRM.
**Status:** Workflow design + as-built notes. Describes how fiscal-year performance
data is produced today, how it should be preserved, and what must be built to
compare one fiscal year against the next.

---

## 1. The fiscal year at Micro Image

The company fiscal year runs **December 1 → November 30**, named by the year it
ends in:

| Fiscal Year | Starts | Ends |
|---|---|---|
| **FY2026** | December 1, 2025 | November 30, 2026 |
| **FY2027** | December 1, 2026 | November 30, 2027 |

This boundary is already implemented in code — see
`sales_monitoring/views.py` → `_resolve_month_context()`. Given any month, it
derives the fiscal year (if the month is December, the FY rolls to the next
year), the `fiscal_start`/`fiscal_end` dates, the ordered 12-month list
(Dec…Nov), and a label like `FISCAL YEAR 2026 (DECEMBER 2025 - NOVEMBER 2026)`.
The existing **Group / Team Fiscal Summary** reports already use this to show
monthly won-profit vs quota for a single fiscal year.

> ✅ The **Executive Dashboard** company-target figure is now fiscal-year aligned:
> `CompanyAnnualTarget.year` is read as the fiscal year, and actual profit is
> measured over the Dec→today fiscal window (it previously used the calendar year
> / Jan 1). So the company target, the group/team fiscal summaries, and the FY
> comparison all use the same Dec–Nov definition.

---

## 2. Where the performance data actually lives

All sales performance (won/lost counts, revenue, profit) is **computed live** at
request time from surviving rows in one table: `SalesFunnel`
(`sales_funnel/models.py`).

- A deal becomes revenue when it is **Closed as Won**: `is_closed=True`,
  `deal_outcome='won'`, and `closed_date` set to the day it closed.
- **Revenue** = `retail` (SRP). **Profit** = `retail − cost` (a computed
  property, not a stored column). FY figures are produced with
  `Sum('retail')` and `Sum(F('retail') - F('cost'))` filtered by
  `closed_date` within the fiscal window.
- Lost deals (`deal_outcome='lost'`, with a required `lost_reason`) feed win-rate
  and "why we lose" learning.
- Removed/soft-deleted entries (`is_active=False`) drop out of the live
  **pipeline** but the rows survive for audit.

**There is no ledger, no snapshot table, and no stored monthly/annual totals.**
Every report recomputes from the live rows each time it loads.

### Why that matters for year-over-year comparison

Because the numbers are recomputed from mutable rows, a past fiscal year's
figures can **silently change after the year ends**. For example, if someone:

- edits `retail` or `cost` on an old won deal,
- edits a `closed_date`,
- removes (soft-deletes) or restores an entry, or
- a linked proposal's amount changes (for proposal-linked entries, revenue reads
  the proposal's live quoted amount),

then "FY2026 total profit" will read differently next month than it did on
November 30, 2026. For an operational dashboard that's fine. For a **year-over-year
comparison that leadership trusts, it is not** — FY2026 must be *frozen* once the
year closes, so FY2026-vs-FY2027 compares a fixed baseline against the live
current year.

---

## 3. The workflow in plain terms

```
   During FY2026                 At FY2026 close                 During FY2027
 (Dec'25 → Nov'30'26)           (early Dec 2026)              (Dec'26 → Nov'30'27)
 ──────────────────────      ─────────────────────────      ──────────────────────
 Salespeople work the        Admin runs the year-end         Live FY2027 numbers
 funnel: quote, advance,     SNAPSHOT. FY2026 totals are     accrue the same way.
 Close Won/Lost (with        copied into a permanent,        The comparison view
 reason). Numbers are        read-only record — per          shows FY2027 (live)
 LIVE and may still change.  salesperson / group / team /    beside FY2026 (frozen).
                             company, plus quota context.
                             FY2026 is now immutable.
```

The principle: **work live, freeze at year-end, compare frozen-vs-live.**

---

## 4. What a salesperson / manager does (operational, already supported)

Nothing new day-to-day. The existing funnel workflow already captures everything
the fiscal summary needs:

1. **Create** funnel entries (directly, or auto-created from a Proposal).
2. **Advance** them through stages (Pink → Yellow; Green/Blue auto-set by the
   ₱500K threshold).
3. **Close** each deal as **Won** or **Lost** when it resolves. Closing sets
   `closed_date`, which is what places the deal into a fiscal year. A **Lost**
   deal requires a reason (kept for team learning and review).
4. **Do not delete** real deals. Use **Remove** (soft delete, with a reason) only
   to take stale entries out of the pipeline; the row — and its revenue if it was
   ever won — is preserved.

The single most important discipline for accurate FY numbers: **close deals in
the fiscal year they actually close, with the correct `closed_date`.** A deal
closed on Nov 30, 2026 belongs to FY2026; the same deal closed Dec 1, 2026
belongs to FY2027.

---

## 5. What the system does to preserve FY2026 for later comparison

This is the part that needs to be **built** (it does not exist yet). The design:

### 5.1 A persisted FY snapshot (new, to build)

Add a model such as `FiscalYearSummary` that stores, per fiscal year and per
scope, the final numbers as of year-end. Suggested shape:

- **Keys:** `fiscal_year` (e.g. 2026), `scope_type` (`company` | `team` |
  `group` | `salesperson`), `scope_id`.
- **Captured metrics:** won count, lost count, win rate, total revenue
  (`Sum retail`), total profit (`Sum retail − cost`), average deal size, and the
  12 monthly profit figures (Dec…Nov).
- **Target context captured at the same time:** the quota/target that applied
  (annualized `TeamMembership.quota`, `RoleMonthlyQuota`, `AsmPersonalTarget`,
  `SupervisorCommitment`, and the company target), so achievement % is frozen too
  and doesn't drift if quotas are later edited.
- **Provenance:** `generated_at`, `generated_by`, and a note. Immutable once
  written (re-running requires an explicit "regenerate" with an audit log entry).

Storing the numbers (not just re-querying) is what makes FY2026 stable regardless
of later edits to the underlying `SalesFunnel` rows.

### 5.2 A year-end snapshot command (new, to build)

A management command, e.g.:

```
python manage.py snapshot_fiscal_year 2026
```

Run it once, shortly after **November 30, 2026**. It should:

1. Resolve the FY window via the existing `_resolve_month_context` logic
   (`fiscal_start = 2025-12-01`, `fiscal_end = 2026-11-30`).
2. Aggregate won/lost revenue and profit from `SalesFunnel`
   (`deal_outcome` in won/lost, `closed_date` within the window) for every
   salesperson, rolled up to group, team, and company — reusing the same
   aggregation the group fiscal summary already does.
3. Capture the quota/target context for that FY.
4. Write one immutable `FiscalYearSummary` row per scope.

It should be safe to re-run (idempotent): either refuse if a snapshot exists, or
replace-with-audit. A good enhancement is a scheduled reminder (or a hook) in
early December so the snapshot isn't forgotten.

### 5.3 Verify, then rely on the snapshot

After snapshotting, spot-check a few salespeople's frozen FY2026 totals against
the live Group/Team Fiscal Summary for the final month of FY2026 (they should
match on snapshot day). From then on, the comparison view reads FY2026 from the
snapshot, never recomputing it.

---

## 6. Comparing FY2026 vs FY2027

### 6.1 Before FY2026 is snapshotted
Use the existing **Group / Team Fiscal Summary** (`sales_monitoring`): pick a
month inside the fiscal year and it shows that FY's monthly profit vs annualized
quota, exportable to Excel/PDF. This already works for a *single* fiscal year.

### 6.2 After FY2026 is snapshotted (the comparison — now built)
The **Fiscal Year Comparison** page (Sales Funnel → Fiscal Year Comparison)
places two years side by side:

- **FY2026** read from the frozen `FiscalYearSummary` (fixed baseline).
- **FY2027** computed live from `SalesFunnel` for the Dec'26→Nov'30'27 window
  (or from its own snapshot once FY2027 closes).

Present, per scope (company → team → group → salesperson):

| Metric | FY2026 | FY2027 | Δ | % change |
|---|---|---|---|---|
| Total profit | frozen | live | +/− | growth % |
| Total revenue | frozen | live | +/− | growth % |
| Won deals | frozen | live | +/− | growth % |
| Win rate | frozen | live | +/− pts | — |
| Avg deal size | frozen | live | +/− | growth % |
| Quota attainment % | frozen | live | +/− pts | — |

It includes a month-by-month (Dec…Nov) overlay so you can see *when* in the year
the two diverge, an exec/AVP scope picker (company → team → group), a Full-year
vs Same-period-YTD toggle, and **Excel + PDF export**.

### 6.3 Fair-comparison notes
- **Compare like windows.** Mid-FY2027, use the **Same-period (YTD)** mode so
  FY2027-to-date is compared against FY2026's *same* Dec–through-current-month
  window, not the full FY2026 — otherwise a partial year looks like a decline.
  Both "Full prior year" and "Same period (YTD)" modes are available in the
  window selector.
- **Company target is fiscal-year aligned.** `CompanyAnnualTarget.year` is the
  fiscal year, and the Executive Dashboard measures company attainment over the
  Dec–Nov window — so the company attainment line matches the fiscal definition
  used everywhere else. When setting a target, enter the fiscal year (the year
  the FY *ends* in), e.g. 2026 for Dec 2025 → Nov 2026.

---

## 7. Roles & permissions

- **Snapshot command / regenerate:** admin (and GM/VP by request). It's a
  year-end, system-of-record action — not something salespeople run.
- **View the FY comparison:** scoped like the existing dashboards — a salesperson
  sees their own FY-vs-FY, supervisor/ASM/SM/AVP see their teams, GM/VP/admin see
  company-wide. (Reuse the funnel role-scoping helpers.)
- **Edits to closed deals after a snapshot:** allowed operationally, but they no
  longer change the frozen FY — only the live current year. If a correction to a
  past FY is genuinely needed, it goes through an explicit "regenerate snapshot"
  with an audit trail, decided by leadership.

---

## 8. Build checklist (what exists vs what's needed)

**Already in place**
- [x] Dec–Nov fiscal boundary logic (`_resolve_month_context`).
- [x] Single-FY group/team summaries + Excel/PDF export.
- [x] Live won/lost revenue & profit from `SalesFunnel`; `deals_history` with a
      `closed_date` date range.
- [x] Quota/target models (`TeamMembership.quota`, `RoleMonthlyQuota`,
      `SupervisorCommitment`, `AsmPersonalTarget`, `CompanyAnnualTarget`).

**Built (implemented)**
- [x] `FiscalYearSummary` snapshot model (immutable per FY per scope, incl. quota
      context) + `FiscalYearSnapshotLog` audit — `sales_monitoring/models.py`,
      migration `0004`. Registered read-only in Django admin.
- [x] Shared fiscal module `sales_monitoring/fiscal.py` (`fiscal_window`,
      `fiscal_year_for_date`, `fiscal_months`, `compute_scope_performance`) — the
      single source of truth for the Dec–Nov window and live aggregation.
- [x] `snapshot_fiscal_year <year>` management command — idempotent (refuses to
      overwrite without `--force`), supports `--dry-run`, writes one row per
      salesperson/group/team/company, and logs every run. Freezes quota context
      too.
- [x] Fiscal Year Comparison view + template (`sales_monitoring:fiscal_year_comparison`),
      role-scoped (execs → company; others → own), showing the chosen FY vs the
      prior FY with Δ and % change, labelling each year **Frozen** (snapshot) or
      **Live**. Linked under the Sales Funnel nav dropdown.
- [x] **Excel + PDF export** of the comparison (metrics table + month-by-month
      overlay). URLs `export_fiscal_year_comparison_excel` / `_pdf`.
- [x] **Month-by-month (Dec–Nov) overlay** showing each month's profit for both
      years side by side.
- [x] **Same-period-YTD mode** (`?mode=ytd`): compares the Dec-through-current-
      month window of the live year against the *same* window of the prior year,
      so a partial year isn't unfairly judged against a full one. (YTD is always
      computed live, since snapshots store full-year figures.)
- [x] **Team / group / salesperson scope picker** for execs/AVPs
      (`?scope_type=&scope_id=`); AVPs are restricted to their own teams/groups,
      and non-execs stay pinned to their own salesperson scope.

- [x] **Reconciled `CompanyAnnualTarget` to the Dec–Nov fiscal year.**
      `CompanyAnnualTarget.year` now means the fiscal year (named by its end
      year). The Executive Dashboard reads the target for the current fiscal year
      and measures actual profit over the Dec→today fiscal window (previously it
      used the calendar year / Jan 1). The "Update Company Annual Target" screen
      defaults to and labels the fiscal year, and the snapshot command matches it
      exactly. No migration needed — the field is unchanged, only its meaning and
      the windows that use it.

**Still to build / enhance**
- [ ] Optional: early-December reminder/hook to run the snapshot.

---

## 8a. When to run `snapshot_fiscal_year` (year-end procedure)

**Run it once, early in December, right after the fiscal year has ended.**
A fiscal year ends on **November 30**; wait until Dec 1 or later so every
November deal is closed and counted, then freeze it.

| Fiscal year | Ends | Run the snapshot | Command |
|---|---|---|---|
| FY2026 | Nov 30, 2026 | On/after **Dec 1, 2026** (early December) | `python manage.py snapshot_fiscal_year 2026` |
| FY2027 | Nov 30, 2027 | On/after **Dec 1, 2027** | `python manage.py snapshot_fiscal_year 2027` |

**Who runs it:** an admin (or GM/VP by request), on the server. It's a
system-of-record action, not something salespeople do.

**Step by step:**
1. Make sure all November deals are closed as Won/Lost with the correct
   `closed_date`. Chase down any still-open deals that actually resolved in the
   fiscal year.
2. Preview first (writes nothing):
   `python manage.py snapshot_fiscal_year 2026 --dry-run`
3. Freeze it:
   `python manage.py snapshot_fiscal_year 2026`
4. Spot-check: open **Sales Funnel → Fiscal Year Comparison**, pick FY2026 — it
   should show the **Frozen snapshot** badge, and its totals should match the
   live Group/Team Fiscal Summary for the final month of FY2026 (they match on
   snapshot day).

**Guardrails:**
- The command **refuses to overwrite** an existing snapshot. If you genuinely
  need to re-freeze (e.g. a corrected deal), re-run with `--force` — this is
  recorded in `FiscalYearSnapshotLog` with who/when.
- **Don't snapshot a year that hasn't ended.** Snapshotting the current,
  in-progress fiscal year would freeze a partial result and misrepresent it. Use
  the comparison view's live/YTD mode to track the current year instead.
- After a year is frozen, later edits to its deals change only the live view,
  never the snapshot — so comparisons stay stable.

### Quick command reference

```
python manage.py snapshot_fiscal_year 2026            # freeze FY2026 (after Nov 30 2026)
python manage.py snapshot_fiscal_year 2026 --dry-run  # preview totals, write nothing
python manage.py snapshot_fiscal_year 2026 --force    # regenerate an existing snapshot (audited)
```

Then open **Sales Funnel → Fiscal Year Comparison** and pick the year. Use the
**window** control for Full-year vs Same-period-YTD, the **scope** picker
(execs) to drill into a team/group, and the **Excel / PDF** buttons to export.

---

## 9. One-paragraph summary for leadership

Throughout FY2026 (Dec 1 2025 – Nov 30 2026), the team works the funnel and
closes deals as Won/Lost; the system computes revenue, profit, and win rate live
from those deals. Right after Nov 30, 2026 we take a **year-end snapshot** that
freezes FY2026's final numbers (and the quotas that applied) into a permanent
record, so they can't drift later. FY2027 then accrues the same way, and a
Fiscal Year Comparison report shows FY2027 beside the frozen FY2026 — per
salesperson, group, team, and company — with growth percentages and a
month-by-month view, so leadership can see exactly where performance improved or
slipped year over year.
