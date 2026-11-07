# Pipeline Health & Forecast Intelligence — Feasibility Plan

**Audience:** GM/VP, President, AVPs, Sales Operations, and whoever maintains the CRM.
**Status:** Proposal for management approval. **No code has been written.** This document
assesses what the CRM can already answer today, what is partially answerable, and what
would require new data capture before it can be built.

---

## 1. Purpose

Management requested a set of sales-intelligence questions grouped under five themes:

1. Pipeline Health & Forecast Accuracy
2. Team Performance & At-Risk Reps
3. Market & Competitor Signals
4. Cross-Functional Alignment (Marketing & Product)
5. Technology & Data Integrity

This document answers, for **each question**, three things:

- **Can we answer it today** from data the CRM already stores?
- **If not fully, what is missing?**
- **What would it take to implement it?**

The recommendation is a **phased rollout** that starts with the answers we can give
immediately and defers the ones that need new fields so that we do not build dashboards on
unreliable data.

### How to read the status labels

| Label | Meaning |
|---|---|
| **READY** | The CRM already stores everything needed. Buildable as a read-only report. |
| **PARTIAL** | Core data exists, but a field is free-text, missing, or not period-scoped, so results would be approximate. |
| **NEEDS CAPTURE** | The underlying fact is not recorded at all. A new field/model (and backfill) is required first. |

---

## 2. The data foundation (what the CRM already records)

All sales performance is computed **live** from `SalesFunnel`
(`sales_funnel/models.py`) — there is no ledger and no stored monthly totals. The table
below is the factual base for every feasibility judgement in this document.

| Data point | Where it lives | Notes |
|---|---|---|
| Deal stage | `SalesFunnel.stage` | `quoted`, `closable`, `project`, `services` — a **single current value**, no history |
| Win / loss outcome | `SalesFunnel.deal_outcome` | `active`, `won`, `lost`; plus `is_closed`, `closed_date` |
| Expected close date | `SalesFunnel.expected_close_date` | Indexed; **overwritten in place** (no change history) |
| Lost reason | `SalesFunnel.lost_reason` | **Free text**, required when marking lost |
| Deal value / cost | `SalesFunnel.retail`, `.cost` | `profit` and `profit_margin` are computed properties |
| Probability | `SalesFunnel.probability` | 0–100%, entered by the rep |
| Pipeline removal | `is_active`, `removed_reason`, `removed_at`, `removed_by` | Soft-delete; rows survive for audit |
| Proposal status | `Proposal.status` | `draft`, `sent`, `accepted`, `declined`, `expired` |
| Discount | `Proposal.discount_amount` | **Informational only — does not change totals**; plus `sales_margin_pct` |
| Approval trail | `ProposalApprovalStep` (`status`, `decided_at`, `approver`) | Who approved what, and when |
| Proposal change log | `ProposalChangeLog` | Unstructured JSON `details`, **no stage timestamps** |
| Quotas / targets | `RoleMonthlyQuota`, `AsmPersonalTarget`, `SupervisorCommitment`, `PersonalContribution` | All **monthly**, keyed by `month` |
| Ongoing rep quota | `TeamMembership.quota` | **No period key** — a single current number |
| Company target | `CompanyAnnualTarget.year`, `.amount` | Fiscal-year aligned |
| Activities | `SalesActivity` (+ `CallActivity`, `MeetingActivity`, `EmailActivity`, `ProposalActivity`, `TaskActivity`) | Type, salesperson, customer, status, dates, notes |
| Leads | `Lead.status`, `.lead_score`, `.is_qualified`, `.source`, `.assigned_to` | Status values include `qualified`, `converted`, `lost` |
| Lead source economics | `LeadSource.cost_per_lead`, `.conversion_rate` | Plus `ConversionTracking.days_to_convert`, `.roi` |
| Customer health flags | `Customer.is_active`, `.auto_inactive_flag`, `.lifetime_won_revenue`, `.last_sales_activity_at` | System-maintained |
| Customer audit | `CustomerHistory` | Full before/after change trail |
| Rep start date | `User.date_joined` | No dedicated `hire_date` field |

**Two structural facts matter most for this request:**

> ⚠️ **There is no deal stage-transition history.** `SalesFunnel.stage` is a single current
> value, and `expected_close_date` is overwritten. Anything that needs "how long has this
> been sitting" or "how many times did this slip" **cannot be computed retroactively** —
> we must start recording it.
>
> ⚠️ **`lost_reason` is free text.** It can be displayed and searched, but it cannot be
> trended ("pricing is 40% of losses") until it is categorized.

**Existing platform capability we can reuse:**

- Role scoping helpers in `crm_project/scoping.py` (`scoped_user_ids`) and the per-app
  `can_*` predicates — so every new report inherits the same visibility rules.
- Chart.js 3.9.1 (charts), openpyxl (Excel), `csv`, reportlab (PDF) — already in use.
- Frozen-snapshot pattern via the `snapshot_fiscal_year` management command, for any
  heavy number that should not be recomputed on every page load.
- **No Celery.** Scheduled work is done through management commands (cron). Any nightly
  aggregation must follow that pattern.

---

## 3. Feasibility assessment by theme

### Theme 1 — Pipeline Health & Forecast Accuracy

#### 1.1 Coverage ratios (3x–4x pipeline vs quarterly and annual targets)

**Status: READY**

Open pipeline value is `Sum(retail)` over active `SalesFunnel` rows. Targets already
exist monthly and can be summed into quarters:

- Quarterly target = sum of the three `RoleMonthlyQuota` / `AsmPersonalTarget` /
  `SupervisorCommitment` months in the quarter.
- Annual target = `CompanyAnnualTarget.amount` (fiscal-year aligned, Dec–Nov).

Deliverable: a coverage card showing open pipeline ÷ target per rep, group, team, and
company, with the 3x/4x threshold flagged.

*Caveat to confirm with management:* `TeamMembership.quota` has **no month key**, so it
can only ever give a "current quota" view. Rep-level quarterly coverage should use
`RoleMonthlyQuota` to stay period-correct.

#### 1.2 Stalled deals (high-value deals sitting past expected close date)

**Status: PARTIAL**

We can already flag **active** deals whose `expected_close_date` is in the past — the
field is indexed, so this is fast even on a large table. This gives "overdue" deals
immediately, filterable by value.

What we cannot do yet: "*sat in the same **stage** past their expected close date*",
because stage entry dates are not recorded. Also, deals with a blank
`expected_close_date` are invisible to this rule.

To close the gap: log stage changes (see Phase 1, below) so we can compute
**days-in-current-stage**, and treat missing close dates as a data-quality signal.

#### 1.3 Deal slippage (rollover month-to-month / quarter-to-quarter)

**Status: NEEDS CAPTURE**

`expected_close_date` is overwritten each time it is edited, so past values are lost. We
cannot currently say "this deal's expected close moved from March to June."

To close the gap: a lightweight **close-date-change log** (old date → new date, who,
when). Once recorded, slippage becomes a straightforward query: count of pushes per deal,
and how many deals cross a month or quarter boundary.

---

### Theme 2 — Team Performance & At-Risk Reps

#### 2.1 Top vs bottom performers (the 80/20, and who misses activity metrics)

**Status: PARTIAL**

The 80/20 revenue view is essentially **already built**: the executive dashboard ranks
individuals by revenue, and `generate_executive_insights` in `sales_monitoring/views.py`
already identifies top performers and zero-revenue reps. Activity **counts** per rep
(calls, emails, meetings) are computable from `SalesActivity`.

The gap is the second half of the question — "*consistently missing activity metrics*".
There is **no activity target model** (e.g. "20 calls / month"), so there is nothing to
measure "missing" against.

To close the gap: a small `ActivityTarget` model (target per rep per month per activity
type), or a simple configurable default. Then "activity attainment" becomes a peer to
quota attainment, which is the more meaningful coaching signal.

#### 2.2 Ramp time for new hires

**Status: PARTIAL**

`User.date_joined` is the only proxy for hire date — there is no dedicated `hire_date` or
onboarding-date field. Because every activity and every won deal is tied to a user, we
can **already** compute a ramp cohort report: for reps who joined in the last N months,
show time-to-first-activity, time-to-first-won-deal, and attainment vs peers.

To make it precise: add an explicit `hire_date` (and optional onboarding milestone dates)
so ramp is measured from the real start date, not the account-creation date.

#### 2.3 Coaching opportunities (where reps lose prospects)

**Status: PARTIAL**

We can link activity volume by type (discovery vs demo vs closing attend) and we know the
funnel **stage** a live deal is in. What is missing is the **stage at which a deal was
lost** — `deal_outcome='lost'` does not record where in the journey it died, and
`lost_reason` is free text.

To close the gap: capture a structured **"lost at stage"** value at the moment a deal is
marked lost, alongside the (categorized) reason. That single field is what turns
"coaching opportunities" from anecdote into a stage-by-stage loss map.

---

### Theme 3 — Market & Competitor Signals

#### 3.1 Lost deal reasons

**Status: PARTIAL**

`lost_reason` is captured for every lost deal and shown in deal history, so the raw
material exists. It is **free text**, so it cannot be grouped or trended.

To close the gap: adopt the pattern already proven elsewhere in this codebase — the
warehouse app's `BacklogReason` lookup. A **`LostReason` category table** (e.g. Pricing,
Feature gap, Brand/reputation, Timing, Competitor, No budget) plus an optional
**competitor name** field would let us report "*what prospects tell us when they leave*"
with real percentages. Historical free text can be backfilled by mapping or manual review.

#### 3.2 Pricing & discounting trends (are reps over-discounting?)

**Status: PARTIAL**

We already store `Proposal.discount_amount`, `sales_margin_pct`, `total_cost`,
`gross_profit`, `approval_total_php`, and the full approval chain in
`ProposalApprovalStep`. So we can chart discount and margin by rep, by group, and over
time, and we can see which discounting went through approval.

Two limitations to flag:

- `discount_amount` is documented as **"informational; does not change totals"** — it is
  not a discount percentage and may be used inconsistently across reps.
- The approval threshold is based on **total amount**, not discount depth, so the system
  cannot currently detect "deep discount that slipped under approval."

To close the gap: add an explicit **discount percentage** field (or derive and store it)
and consider a discount-depth approval rule. Until then, the report is directional, and we
should state that on the dashboard.

#### 3.3 Buyer journey shifts (longer decisions, more stakeholders)

**Status: NEEDS CAPTURE**

This needs two things we do not have: the **time spent in each stage** (no stage history)
and the **number of stakeholders** involved in a decision (`CustomerContact` stores
contacts per customer, but nothing ties a count to an individual deal).

To close the gap: stage-transition history (Phase 1) plus an optional
"decision-makers involved" count on the deal. Then "deals are taking longer and need more
sign-offs" becomes measurable rather than anecdotal.

---

### Theme 4 — Cross-Functional Alignment (Marketing & Product)

#### 4.1 Lead quality — MQL / SQL

**Status: PARTIAL**

The lead module is comparatively rich: `Lead.status` (including `qualified`),
`Lead.lead_score`, `Lead.is_qualified`, `LeadSource.cost_per_lead`, `LeadSource.conversion_rate`,
and `ConversionTracking` (`.days_to_convert`, `.acquisition_cost`, `.roi`). So we can
**already** report cost per lead, cost per conversion, conversion rate by source, and
scoring distribution — which answers most of "is marketing delivering qualified leads?"

The specific gap: there is **no explicit MQL vs SQL distinction**. The nearest value is
`qualified`. Also, `SalesActivity` is **not linked to leads**, so we cannot yet tie a rep's
activity effort to the quality of leads they received.

To close the gap: either map the existing `qualified` status to an agreed MQL/SQL
definition, or add a dedicated qualification stage. Link activities to leads if management
wants "effort spent on junk leads" reporting.

#### 4.2 Product roadblocks (recurring feature requests / technical blockers killing deals)

**Status: NEEDS CAPTURE**

No model exists for feature requests or product blockers. The only adjacent data is
`ProposalItem.part_number`, which identifies *what was quoted* but not *what was missing*.

To close the gap: a structured **blocker/feature-request** reason captured on lost or
stalled deals (can share the `LostReason` table), optionally referenced to a product or
part. Aggregated over time this produces the "top 10 blockers killing deals" list.

#### 4.3 Customer success handoffs / early churn signs

**Status: PARTIAL**

`Customer` already carries useful health signals: `is_active`, `auto_inactive_flag`,
`lifetime_won_revenue`, `last_sales_activity_at`, `status_last_synced_at`, and the full
`CustomerHistory` audit trail. `DelinquencyRecord` covers payment delinquency. So
**at-risk account** detection is partly possible today: e.g. won revenue followed by a long
silence, or an inactivity flag raised shortly after onboarding.

What is missing is an explicit **handoff / onboarding** record (was the account properly
set up?) and a **renewal date**. Without those we can spot churn signals but cannot prove
they stem from over-promising at handoff.

To close the gap: a lightweight onboarding checklist record plus a renewal/contract date.

---

### Theme 5 — Technology & Data Integrity

#### 5.1 CRM hygiene ("garbage in, garbage out")

**Status: READY**

This is the most immediately valuable item and needs **no new data**, because the missing
data *is* the metric. We can build a data-quality scorecard today measuring, for example:

| Hygiene check | Source |
|---|---|
| Active deals with no `expected_close_date` | `SalesFunnel` |
| Lost deals with empty / very short `lost_reason` | `SalesFunnel` |
| Deals not updated in N days | `SalesFunnel.updated_at` |
| Activities completed with no `notes` / outcome | `SalesActivity` |
| Customer status flags out of sync | `Customer.status_last_synced_at` |
| Reps with no activity in N days | `User.last_activity`, `SalesActivity` |

This is a strong "quick win" for Phase 0 because it improves the reliability of every
other report on this list.

#### 5.2 Sales velocity (first touch → signed contract)

**Status: PARTIAL**

Two velocity legs are computable now:

- **Lead → customer**: `ConversionTracking.days_to_convert` is already stored.
- **Funnel creation → close**: `SalesFunnel.date_created` → `closed_date`.

So we can already trend cycle length over time and answer "is the cycle lengthening?" for
these two legs. The full "first touch → signed contract" chain, and any per-stage
breakdown of where time is lost, needs the stage-transition history described earlier.

---

## 4. Summary matrix

| # | Question | Status | Blocking gap |
|---|---|---|---|
| 1.1 | Pipeline coverage vs targets | **READY** | — |
| 1.2 | Stalled high-value deals | **PARTIAL** | No stage-entry dates |
| 1.3 | Deal slippage / rollover | **NEEDS CAPTURE** | Close-date history |
| 2.1 | Top vs bottom performers | **PARTIAL** | No activity targets |
| 2.2 | Ramp time for hires | **PARTIAL** | No `hire_date` |
| 2.3 | Coaching by loss stage | **PARTIAL** | No "lost at stage" |
| 3.1 | Lost deal reasons | **PARTIAL** | Free-text only |
| 3.2 | Pricing / discounting trends | **PARTIAL** | Discount is informational |
| 3.3 | Buyer journey shifts | **NEEDS CAPTURE** | Stage history + stakeholders |
| 4.1 | Lead quality (MQL/SQL) | **PARTIAL** | No MQL/SQL split |
| 4.2 | Product roadblocks | **NEEDS CAPTURE** | No blocker model |
| 4.3 | CS handoffs / churn | **PARTIAL** | No handoff / renewal record |
| 5.1 | CRM hygiene | **READY** | — |
| 5.2 | Sales velocity | **PARTIAL** | Stage timestamps for full chain |

**Bottom line:** roughly a third of the request is answerable from today's data, and most
of the rest becomes answerable after a small number of new fields. Only three items
(slippage, buyer-journey shifts, product roadblocks) require genuinely new capture models.

---

## 5. Proposed delivery phases

Each phase is scoped so management can approve, then verify, before the next begins.
Sizing is **complexity**, not calendar time: **S** = no schema change, **M** = new
field/view or small model, **L** = new model + history + multiple dashboards.

### Phase 0 — Read-only wins (no schema change) · **S**

Buildable immediately, no migrations, lowest risk. Delivers a new
"Pipeline Intelligence" area under Sales Monitoring:

- Pipeline coverage card (vs quarterly and annual targets).
- Overdue / stalled deals list (active deals past `expected_close_date`).
- Top vs bottom performer view (revenue + activity counts).
- Lead source quality and conversion report.
- **CRM hygiene scorecard** (Theme 5.1).
- Sales velocity trends for achievable legs (Theme 5.2).
- Discount & margin trend (clearly labelled as directional).

*Recommendation: approve Phase 0 first. It needs no data changes, delivers value
immediately, and its hygiene scorecard will show us how trustworthy the later phases will be.*

### Phase 1 — Capture the missing facts · **M**

Small, well-understood schema additions that unblock the most questions:

| Addition | Unblocks |
|---|---|
| `LostReason` category lookup + optional competitor name | 3.1, and reporting for 2.3 / 4.2 |
| Close-date change log (old → new, who, when) | 1.3 |
| Stage-transition history (stage, entered-at, changed-by) | 1.2, 2.3, 3.3, 5.2 |
| `ActivityTarget` (per rep / month / type) | 2.1 |
| Explicit `User.hire_date` | 2.2 |

Follows the codebase's existing custom-audit pattern (as used by `DeliveryEvent` and
`CustomerHistory`). Historical `lost_reason` free text can be backfilled into categories
by mapping.

### Phase 2 — Deeper analytics · **L**

- Buyer journey dashboards (decision cycle, stakeholder counts).
- Product roadblock / feature-request aggregation.
- Customer success handoff checklist + renewal date → early-churn watchlist.
- Nightly pre-computation via a management command (cron), following the existing
  `snapshot_fiscal_year` pattern, so heavy aggregations stay fast.

### Phase 3 — Forecast accuracy & governance (optional) · **L**

- Forecast vs actual by period, using `probability` weighted pipeline.
- Data-quality SLAs and rep-level hygiene coaching reports.

---

## 6. Roles & access (proposed)

New reports should reuse the existing scoping layer (`scoped_user_ids`) so visibility is
consistent with the rest of the CRM:

| Report area | Proposed visibility |
|---|---|
| Pipeline coverage, slippage, forecast | Executive (GM/VP/President/Admin), AVPs (own teams) |
| Team performance, activity attainment, ramp | Supervisors / ASMs / SMs (their groups), AVPs, Executives |
| Lost reasons, product roadblocks, buyer journey | Executives + Marketing (read-only, aggregated) |
| Lead quality / MQL-SQL | Marketing + Executives |
| CRM hygiene scorecard | Executives and each manager for their own team |

Individual-rep data should follow the same rules already applied to the individual
performance rankings (inactive / unassigned reps excluded).

---

## 7. Risks, assumptions & open questions for management

**Risks**

1. **Data quality gates every number.** Until the hygiene scorecard (5.1) shows the inputs
   are reliable, later dashboards risk being "precise but wrong". We recommend Phase 0 first
   for this reason.
2. **No backfill for history.** Stage-slippage and time-in-stage can only be measured
   **from the day we start recording**; earlier deals will not have it.
3. **Definition drift.** Terms like "MQL", "SQL", "coverage", and "stalled" must be agreed
   business definitions before build, or reports will be argued about rather than used.
4. **`discount_amount` semantics.** Because it is informational today, discounting trends
   are directional until a real discount-percentage field is agreed.
5. **No Celery.** Heavy aggregations must be pre-computed by scheduled management commands
   (cron) rather than a task queue.

**Assumptions**

- Fiscal year remains December 1 → November 30.
- Quotas stay monthly (quarterly derived by summation).
- Reports are read-only; we are not proposing to change how reps enter deals.

**Open questions for management**

1. What is the agreed **coverage** threshold (3x, 4x) and against which target (rep,
   group, team, company)?
2. How do we define **"stalled"** — X days in the same stage, or past
   `expected_close_date`, or both?
3. Do we need a formal **MQL/SQL** distinction, or is the existing `qualified` lead
   status sufficient?
4. Should **competitor name** be a required field on lost deals?
5. Is a **discount-percentage** field (and possibly a discount-depth approval rule)
   approved?
6. Which roles may see **individual rep** hygiene and ramp data?

---

## 8. Approval

Please indicate approval to proceed, and to which phase:

| Item | Decision |
|---|---|
| Approve Phase 0 (read-only, no schema change) | ☐ Yes ☐ No |
| Approve Phase 1 (new fields: loss reasons, slippage, stage history, activity targets, hire date) | ☐ Yes ☐ No |
| Approve Phase 2 (buyer journey, product roadblocks, CS handoffs, nightly pre-compute) | ☐ Yes ☐ No |
| Approve Phase 3 (forecast accuracy & governance) | ☐ Yes ☐ No |

**Open questions to be answered before build:** items 1–6 in Section 7.

> Once approved, Phase 0 requires no database migration and can begin immediately; Phases
> 1–3 will each be delivered as a separate, reviewable change with its own migration and
> tests.
