# Technical Sales Role — Feasibility & Implementation Plan

**Status:** Proposed — awaiting management approval
**Author:** Engineering
**Target module(s):** `users`, `teams`, `customers`, `sales_funnel`, `sales_proposals`, `sales_monitoring`, `templates`
**Related existing concepts:** `techmgr` / `asst_techmgr` roles, `tsg` (Technical Sales Group) group type, `Team.tech_manager`

---

## 1. Summary

Management wants to add a **Technical Sales** function under the **Technical / Engineering department**. Technical Sales staff sell and support:

- Parts sales
- Services
- Repair
- In-house support
- Remote support

**Staffing & assignment rules requested:**

1. **Two Technical Sales people is the ideal setup** — one handles the existing customers of **Team A**, the other handles the existing customers of **Team B**.
2. **If there is only one Technical Sales person**, there must be an option for that single person to **handle all customers of both Team A and Team B**.
3. Technical Sales is **supervised directly by the Technical Manager (`techmgr`) or Assistant Technical Manager (`asst_techmgr`)** — not by a sales Supervisor/ASM/AVP.

**Verdict: Doable, and the codebase is already partly prepared for it.** The system already has the `techmgr`/`asst_techmgr` roles, a `tsg` ("Technical Sales Group") group type, and a `Team.tech_manager` link. What is missing is (a) a dedicated **Technical Sales** staff role, (b) wiring that role into the customer-visibility, funnel, proposal, and monitoring scoping, and (c) a clean way to scope a Technical Salesperson to one team's customers or to all teams' customers.

No architectural blockers were found. This is an additive change that follows patterns already used for the `asm`/`sm` ("Sales Manager") roles.

---

## 2. What already exists (confirmed in code)

| Capability | Location | Notes |
|---|---|---|
| Technical Manager / Assistant Technical Manager roles | `users/models.py` → `ROLE_CHOICES` (`techmgr`, `asst_techmgr`) | Already selectable roles. |
| Team ↔ Technical Manager link | `teams/models.py` → `Team.tech_manager` FK (`limit_choices_to={'role__in':['techmgr','asst_techmgr']}`) | A team can be headed by a Technical Manager. |
| Technical Sales **Group** type | `teams/models.py` → `Group.GROUP_TYPE_CHOICES` includes `('tsg', 'Technical Sales Group')` | TSG groups have **no supervisor**; `Group.get_manager()` returns `team.tech_manager`. |
| TSG supervision resolution | `teams/models.py` → `Group.get_manager()`, `get_manager_role()`, `is_tsg()` | Already returns the Technical Manager (or Assistant) as the manager of a TSG group. |
| Team/Group management access for technical roles | `teams/views.py` → `can_view_teams`, `can_manage_groups` include `techmgr`, `asst_techmgr` | Technical roles can already view/manage teams & groups. |
| Role is a plain `CharField(choices=...)` | `users/models.py` → `role` field | Adding a role = edit choices + `makemigrations`/`migrate`. |

**Key gap:** `techmgr`/`asst_techmgr` are currently wired **only** into the `teams/` module. They have **no scoping** in `customers`, `sales_funnel`, `sales_proposals`, or `sales_monitoring`, are **absent from the navbar gates** in `templates/base.html`, and are **not in the proposal `ROLE_LEVEL` ladder**. There is **no "Technical Sales" staff role** yet (only the two manager roles).

---

## 3. Important design constraints discovered in the code

These shaped the plan and must be respected:

1. **No centralized permission system.** Every role check is hand-coded: helper functions (`visible_customers_queryset`, `visible_funnel_entries`, `visible_proposals_queryset`), per-view `if user.role == ...` branches, `user_passes_test` predicates, and `{% if user.role in '...' %}` template gates. A new role is **invisible until explicitly added to each place**. (See Section 7 for the full checklist.)

2. **Default fall-through differs dangerously by module.** `visible_proposals_queryset` and `visible_funnel_entries` **default to "see everything"** for unhandled roles, while `customers` and `sales_monitoring` **default to "see nothing."** → A new role **must be handled explicitly in the proposals and funnel helpers**, otherwise a Technical Salesperson would see *all* proposals/funnel entries company-wide. This is the single most important correctness item.

3. **`Customer.salesperson` is the ownership field** (`customers/models.py`), with `limit_choices_to={'role__in': ['salesperson','supervisor','asm','sm','avp'], 'is_active': True}`. The new Technical Sales role must be added here if Technical Sales should **own/be assignable to** customers.

4. **Team A / Team B are just `Team` rows** (no hardcoded A/B). "Handle Team A's customers" means "handle customers belonging to that Team's salespeople." Scoping to **one or both** teams is the crux of the feature.

5. **TSG groups must not have a supervisor** (`Group.clean()`), and their manager is resolved from `team.tech_manager`. This matches "supervised by the Technical Manager."

6. **`asm`/`sm` ("Sales Manager") scoping is the ideal template** to copy. They use a group/team-scoped membership pattern (`asm_scoped_groups`, `sm_groups`, `group_scoped_member_ids`) that we can mirror for Technical Sales — the difference being Technical Sales is scoped by **team(s)** rather than groups.

---

## 4. Proposed design

### 4.1 New role: `technical_sales`

Add one new role to `User.ROLE_CHOICES`:

```python
('technical_sales', 'Technical Sales'),
```

Keep `techmgr` / `asst_techmgr` as the **supervisor** roles (already exist). Technical Sales staff are the individual contributors supervised by them.

### 4.2 How a Technical Salesperson is scoped to Team A / Team B / both

The requirement is: TS#1 → Team A customers, TS#2 → Team B customers; and if only one TS → both teams. This is a **many-to-many between Technical Sales users and Teams**. Two options evaluated:

**Option A (RECOMMENDED): a `technical_sales_teams` M2M from `Team` (or a through-field on the user).**
Add an M2M so a Technical Salesperson can be attached to **one or more Teams**:

```python
# teams/models.py — on Team
technical_sales = models.ManyToManyField(
    User,
    related_name='ts_teams',
    blank=True,
    limit_choices_to={'role': 'technical_sales'},
    help_text='Technical Sales staff who handle this team\'s customers.',
)
```

- Two TS people → each attached to their one team (TS#1 → Team A, TS#2 → Team B).
- One TS person → attach that single user to **both** Team A and Team B → they see all customers of both.
- Fully configurable from the Team edit screen; no code change needed when staffing changes.
- Mirrors the existing `Team.asm` / `sm_managers` pattern (team/group‑scoped managers).

**Option B (rejected): reuse the TSG `Group` + `TeamMembership`.**
Put Technical Sales users into a `tsg` group via `TeamMembership`. Rejected because: a `TeamMembership` is **one group per user** (`OneToOneField`), so a single TS person could not span two teams without hacks; and the "handle all customers of both teams" case would be awkward. Option A handles the 1-vs-2 staffing cleanly.

> We will still **optionally** create a `tsg` Group per team for org-chart display (it already renders a "Technical Sales" badge on the AVP dashboard), but **visibility** will be driven by the `Team.technical_sales` M2M, which is the reliable scoping source.

### 4.3 Customer visibility for `technical_sales`

Add a branch to `customers/permissions.py` → `visible_customers_queryset(user)`:

```python
if user.role == 'technical_sales':
    team_ids = user.ts_teams.values_list('id', flat=True)   # teams they handle
    if not team_ids:
        return Customer.objects.none()
    scoped_users = get_team_scoped_users(team_ids, roles=ASSIGNABLE_ROLES)
    return Customer.objects.filter(salesperson_id__in=scoped_users.values_list('id', flat=True))
```

This says: *a Technical Salesperson sees every customer owned by any salesperson/supervisor/etc. in the team(s) they are attached to.* Attaching to both teams → sees both teams' customers. This directly satisfies the 1-vs-2 staffing rule.

**Decision needed from management (see Section 9):** Do Technical Sales staff **own** customers, or only **view/support** customers owned by the corporate account managers? This determines whether we add `technical_sales` to `Customer.salesperson.limit_choices_to` and to `ASSIGNABLE_ROLES`. The recommended default is **view/support only** (they service existing customers, they don't take ownership away from the account manager).

### 4.4 Supervision by Technical Manager / Assistant Technical Manager

- The Technical Manager (`techmgr` / `asst_techmgr`) is linked to a team via the existing `Team.tech_manager` FK.
- A Technical Manager's visibility = union of customers/funnel/proposals of the Technical Sales staff attached to **their** team(s) (`user.tsg_managed_teams`). We add `techmgr`/`asst_techmgr` branches to the scoping helpers using that reverse relation.
- This makes the chain **Technical Sales → Technical Manager / Assistant Technical Manager**, exactly as requested, independent of the sales Supervisor/ASM/AVP ladder.

### 4.5 Technical Sales offerings (parts, services, repair, in-house/remote support)

These five offerings are **what Technical Sales sells**. Two levels of support, phased:

- **Phase 1 (MVP):** Represent offerings as a **category/tag** on existing records so Technical Sales can use the current Proposal and Sales Funnel flows for parts/services/repair quotes. Add an optional `offering_type` choice field (`parts`, `services`, `repair`, `inhouse_support`, `remote_support`) to the Sales Funnel entry and/or Proposal so technical deals are classified and reportable. Low effort, reuses all existing proposal/funnel machinery.
- **Phase 2 (optional, later):** A dedicated "Technical Sales" dashboard and (if needed) a lightweight service/repair ticket linkage to the existing `customer_service` app. Deferred until Phase 1 is validated.

---

## 5. Scope of changes by module

### 5.1 `users` (role definition)
- Add `('technical_sales', 'Technical Sales')` to `User.ROLE_CHOICES`.
- Add an appropriate `JOB_TITLE_CHOICES` entry if desired (display only).
- Migration: `AlterField` on `User.role` (mechanical, like prior role additions `0003/0009/0011`).

### 5.2 `teams` (assignment + supervision structure)
- Add `Team.technical_sales` M2M (Section 4.2).
- Surface it in `TeamForm` and the Team edit template so admins/execs attach TS staff to Team A/B (or both to one person).
- (Optional) allow creating a `tsg` Group per team for the org chart.
- Add a small helper, e.g. `technical_sales_team_ids(user)` and/or `tech_manager_team_ids(user)`, mirroring `asm_scoped_groups`.
- Migration: add the M2M table.

### 5.3 `customers` (visibility & assignment)
- `permissions.py`: add `technical_sales`, `techmgr`, `asst_techmgr` branches to `visible_customers_queryset`, `can_view_customer`, `can_edit_customer`, `assignment_targets_queryset`, and `get_user_team_ids`.
- **If** management wants TS to own customers: add `technical_sales` to `Customer.salesperson.limit_choices_to` and to `ASSIGNABLE_ROLES` (migration for `limit_choices_to` change is cosmetic/no-op at DB level but should still be generated).
- Decide whether TS can **edit** (`can_edit_customer`) or only **view** (`can_view_customer`) — recommended: view + add service notes, not reassign ownership.

### 5.4 `sales_funnel` (CRITICAL — avoid "see all" default)
- `visible_funnel_entries(user)`: add explicit `technical_sales`, `techmgr`, `asst_techmgr` branches scoped by team. **Must be explicit** because the default is "see everything."
- `can_access_funnel` / `is_manager`: add the new roles if TS should use the funnel for parts/service deals.
- (Phase 1) optional `offering_type` field on the funnel entry.

### 5.5 `sales_proposals` (CRITICAL — avoid "see all" default + approval)
- `visible_proposals_queryset(user)`: add explicit `technical_sales`, `techmgr`, `asst_techmgr` branches (scoped by team / `created_by`). **Must be explicit** (default is "see all").
- `Proposal.get_approval_chain()` → `ROLE_LEVEL`: insert the new roles into the authority ladder, e.g. `technical_sales: 1` (same tier as salesperson) and `techmgr`/`asst_techmgr` at a supervisor-equivalent level (e.g. `3`), so a Technical Sales proposal routes to the Technical Manager for approval instead of the sales Supervisor/AVP.
- Define the technical approval chain: **Technical Sales → Technical Manager (or Assistant) → (threshold-based exec approval if required).** Reuse `ProposalApprovalTier`; the chain resolution needs a branch that, when the creator is `technical_sales`, resolves the approver from the team's `tech_manager` rather than the group supervisor.

### 5.6 `sales_monitoring` (dashboards)
- Add `technical_sales` to the dashboard dispatcher (route to salesperson-style dashboard, or a dedicated TS dashboard in Phase 2).
- Add `techmgr`/`asst_techmgr` to the dispatcher so Technical Managers get a team-scoped view of their Technical Sales staff.
- `RoleMonthlyQuota.limit_choices_to`: add `techmgr`/`asst_techmgr` (and optionally `technical_sales`) if Technical Sales/Technical Managers get monthly quotas.

### 5.7 `templates/base.html` (navbar)
- Add `technical_sales`, `techmgr`, `asst_techmgr` to the relevant `{% if user.role in '...' %}` gates (Customers, Proposals, Funnel, Monitoring, Files) so these users see the right nav items. Currently the technical roles see **almost no nav**.

---

## 6. Data model changes (summary)

| Model | Change | Migration type |
|---|---|---|
| `users.User` | Add `technical_sales` to `ROLE_CHOICES` (and optional job title) | `AlterField` |
| `teams.Team` | Add `technical_sales` M2M (TS staff ↔ teams) | `AddField` (M2M table) |
| `customers.Customer` | *(Only if TS owns customers)* add `technical_sales` to `salesperson.limit_choices_to` | `AlterField` (no-op at DB) |
| `sales_funnel.SalesFunnel` | *(Phase 1, optional)* add `offering_type` choice | `AddField` |
| `sales_proposals.Proposal` | *(Phase 1, optional)* add `offering_type` choice | `AddField` |
| `teams.RoleMonthlyQuota` | *(If TS/TM get quotas)* add roles to `limit_choices_to` | `AlterField` (no-op at DB) |

All changes are additive and backward-compatible. No destructive migrations.

---

## 7. Implementation checklist (where a new role must be wired)

Because permissions are hand-coded, the new role(s) must be added to **every** location below. This list is the authoritative "definition of done":

- [ ] `users/models.py` — `ROLE_CHOICES` (+ migration)
- [ ] `teams/models.py` — `Team.technical_sales` M2M (+ migration); helper(s) for TS/TM team scoping
- [ ] `teams/forms.py` — expose `technical_sales` in `TeamForm`
- [ ] `teams/` templates — Team edit screen shows the TS assignment field
- [ ] `customers/permissions.py` — `visible_customers_queryset`, `can_view_customer`, `can_edit_customer`, `assignment_targets_queryset`, `get_user_team_ids` (+ `ASSIGNABLE_ROLES`/`EXEC_ROLES` if applicable)
- [ ] `customers/models.py` — `Customer.salesperson.limit_choices_to` (only if TS owns customers)
- [ ] `customers/views.py` — `is_manager`-style predicates if TS/TM need management screens
- [ ] `sales_funnel/views.py` — `visible_funnel_entries` (**explicit branch**), `can_access_funnel`, `is_manager`
- [ ] `sales_proposals/views.py` — `visible_proposals_queryset` (**explicit branch**)
- [ ] `sales_proposals/models.py` — `ROLE_LEVEL` ladder + `get_approval_chain()` technical branch
- [ ] `sales_monitoring/views.py` — dashboard dispatcher + per-view role branches
- [ ] `teams/models.py` — `RoleMonthlyQuota.limit_choices_to` (if quotas apply)
- [ ] `templates/base.html` — navbar role gates
- [ ] `users/views.py` — user-creation flows so admins can create Technical Sales / Technical Manager users
- [ ] Tests — see Section 10

---

## 8. Phased rollout

**Phase 0 — Approval & decisions (this document).** Confirm the open questions in Section 9.

**Phase 1 — Core role & scoping (MVP).**
1. Add `technical_sales` role + `Team.technical_sales` M2M (migrations).
2. Wire customer/funnel/proposal/monitoring visibility (team-scoped) for `technical_sales`, `techmgr`, `asst_techmgr`.
3. Technical approval chain (TS → Technical Manager).
4. Navbar gates.
5. Admin can create TS/TM users and attach TS to Team A / Team B / both.
6. Tests for the 1-TS-both-teams and 2-TS-split-teams scenarios.

**Phase 2 — Offerings & dashboards (optional, after validation).**
1. `offering_type` classification on funnel/proposal (parts / services / repair / in-house / remote).
2. Dedicated Technical Sales dashboard + Technical Manager team view.
3. Optional linkage to `customer_service` tickets for repair/support follow-through.

---

## 9. Open questions for management (please confirm before build)

1. **Ownership vs. support:** Should Technical Sales **own** customers (be a valid `Customer.salesperson`), or only **view/support** customers owned by the Corporate Account Managers? *Recommended: view/support only.*
2. **Edit rights:** May Technical Sales **edit** customer records / add service notes, or strictly read-only? *Recommended: add notes, no reassignment.*
3. **Proposals:** Should Technical Sales **create proposals** (for parts/service/repair quotes)? If yes, confirm the approval chain is **Technical Sales → Technical Manager/Assistant → (exec approval above a ₱ threshold)**.
4. **Quotas:** Do Technical Sales and/or Technical Managers carry **monthly quotas / targets** (so they appear in Sales Monitoring), or are they excluded from quota tracking?
5. **Team scope default:** If a Technical Salesperson is attached to **no** team, should they see **nothing** (recommended, safe) or **everything**?
6. **Offerings tracking (Phase 2):** Is classifying deals by offering type (parts/services/repair/in-house/remote) required now, or later?

---

## 10. Risks & mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| New role defaults to "see everything" in proposals/funnel | Data over-exposure | **Add explicit role branches** in `visible_proposals_queryset` and `visible_funnel_entries` (called out as CRITICAL). Add a regression test asserting a TS with no team sees nothing. |
| Role wired in some modules but not others (partial rollout) | Confusing/broken UX, hidden data | Use the Section 7 checklist as "definition of done"; code review against it. |
| Single-TS-both-teams vs two-TS-split not configurable later | Rework when staffing changes | `Team.technical_sales` M2M makes staffing a data change, not a code change. |
| Approval chain mis-routes technical proposals to sales managers | Wrong approvers | Explicit `techmgr`/`asst_techmgr` entries in `ROLE_LEVEL` + a technical branch in `get_approval_chain()`; tests on chain resolution. |
| `limit_choices_to` changes not reflected without migration | Forms show wrong options | Generate the (no-op) `AlterField` migrations so state stays consistent. |

---

## 11. Effort estimate (engineering, excluding management review)

| Phase | Scope | Rough effort |
|---|---|---|
| Phase 1 | Role, M2M, scoping across 5 modules, approval chain, navbar, forms, tests | ~3–5 dev-days |
| Phase 2 | Offerings classification, TS dashboard, optional ticket linkage | ~3–6 dev-days |

Estimates assume no changes to the recommended design and are for implementation + tests + self-QA on a staging DB.

---

## 12. Conclusion

The feature is **feasible and low-risk**. The data model already anticipates a technical sales function (`techmgr`/`asst_techmgr`, `tsg` group type, `Team.tech_manager`). The remaining work is primarily (1) adding a `technical_sales` role, (2) a `Team.technical_sales` M2M to support the "one person → both teams / two people → split teams" rule, and (3) wiring the role into the existing hand-coded scoping helpers — most importantly the proposals and funnel helpers, which otherwise default to exposing all records.

**No code should be written until the Section 9 questions are answered and management approves this plan.**

---

# Addendum A — Technical Sales: Proposals, Auto-Funnel, Customer Search & Manager Visibility

**Status:** Proposed — awaiting management approval (extends the plan above)
**Added behaviors requested:**

1. Technical Sales can **create proposals**, and each proposal is **automatically added as a Sales Funnel entry**.
2. Technical Sales can **search customers** and create a proposal on the resulting customer.
3. The resulting **funnel entries and proposals are visible to the Technical Manager / Assistant Technical Manager**.

**Verdict: Doable with small, well-scoped additions.** Most of the machinery already exists — proposal creation already auto-creates a linked funnel entry for every role. The work is (a) letting `technical_sales` reach the proposal form with a correctly scoped customer list, (b) one data-model fix so the auto-created funnel entry is valid and visible, and (c) the manager-visibility branches already described in Section 5. Details below, grounded in the current code.

## A.1 Proposals auto-create a Sales Funnel entry (already built — reuse as-is)

This behavior **already exists for every proposal author** and does not need to be rebuilt:

- On create **and** update, the proposal views call `update_sales_funnel(proposal)`:
  - `sales_proposals/views.py` — after `ensure_approval_chain()` on create (~line 770) and update (~line 862), and after email send (~line 1748).
  - `sales_proposals/multi_option_views.py` — multi-option create/update (~lines 119, 253).
- `update_sales_funnel(proposal)` (`sales_proposals/views.py` ~line 2075):
  - If a `SalesFunnel` row is already linked to the proposal → updates `retail`, `cost`, `requirement_description`.
  - Else → **creates** a new `SalesFunnel` row linked to the proposal, with `stage='quoted'` (Pink), `deal_outcome='active'`, `customer=proposal.customer`, and **`salesperson=proposal.created_by`**.

So once a Technical Salesperson can create a proposal, the auto-funnel entry happens automatically. **No new sync code is required.**

## A.2 CRITICAL data-model fix: `SalesFunnel.salesperson` constraint

`update_sales_funnel()` sets `salesperson=proposal.created_by`. For a Technical Sales author, `created_by.role == 'technical_sales'`, but:

```python
# sales_funnel/models.py
salesperson = models.ForeignKey(
    User, on_delete=models.CASCADE, related_name='funnel_entries',
    limit_choices_to={'role': 'salesperson'},   # <-- only 'salesperson'
)
```

- `limit_choices_to` is **form/admin-only**, so the ORM `.create(...)` in `update_sales_funnel()` **will not raise** — the row is written. **But** it is semantically wrong (a non-salesperson in a "salesperson" FK) and, more importantly, **the existing funnel scoping filters on `salesperson` relationships**, so a funnel entry owned by a `technical_sales` user would be **invisible** to the normal team/group funnel queries and could leak into the "see all" default.

**Required change:** broaden the field to accept the technical roles and make visibility explicit:

```python
limit_choices_to={'role__in': ['salesperson', 'technical_sales']}
```

Then ensure `visible_funnel_entries(user)` has an **explicit** `technical_sales` branch (`salesperson=user`) and `techmgr`/`asst_techmgr` branches (entries whose `salesperson` is a Technical Sales user attached to the manager's team) — see A.5. Migration: `AlterField` (no-op at DB, keeps state consistent).

> Alternative considered: keep `limit_choices_to` as-is and instead store the Technical Sales author elsewhere. Rejected — it would fork the funnel ownership model and complicate every existing funnel query. Broadening the FK is the minimal, consistent fix.

## A.3 Customer search + create proposal on the result

Two code paths govern which customers a Technical Salesperson can pick/search when creating a proposal:

**(a) The proposal form's customer dropdown is scoped per-role in its own `if/elif` block** — it does **not** reuse `visible_customers_queryset`:

- `sales_proposals/forms.py` → `ProposalForm.__init__` (~lines 94–118) builds `qs = Customer.objects.filter(is_active=True)` then narrows by `role` (`salesperson`, `supervisor`, `teamlead`, `asm`/`sm`, `avp`). There is **no `technical_sales` branch**, so today a TS user would fall through and get the **unfiltered** `is_active=True` queryset (all customers).

  **Change:** add a `technical_sales` branch that scopes to the team(s) the TS user handles (the `Team.technical_sales` M2M from Addendum/Section 4.2), e.g. customers whose `salesperson` is in `get_team_scoped_users(user.ts_teams..., roles=ASSIGNABLE_ROLES)`. Add `techmgr`/`asst_techmgr` branches too (scope by `user.tsg_managed_teams`). This keeps the proposal customer picker consistent with `visible_customers_queryset`.

  > **Tech-debt note (optional):** `ProposalForm.__init__` duplicates role-scoping logic that already lives in `customers/permissions.visible_customers_queryset`. Consider refactoring the form to call that helper so the two never drift. Not required for this feature, but recommended.

**(b) The global navbar search** (`core/views.py` → `global_search`, added previously) already scopes customer results through `visible_customers_queryset(user)`. Once that helper gets the `technical_sales` branch (Section 5.3), a Technical Salesperson can **search a customer in the navbar**, open it, and start a proposal.

**"Create proposal on the result customer" UX:** the proposal create flow already accepts a selected customer. Two low-effort ways to satisfy "search → create proposal on that customer":
- Rely on the proposal form's own (now TS-scoped) searchable customer dropdown; or
- Add a "Create Proposal" action on the customer detail / search-result row that deep-links to the proposal create form with the customer pre-selected (`?customer=<id>`). *(Optional convenience; confirm if wanted.)*

Either way, the gating rule is the same: **a TS user may create a proposal for any customer within the team(s) they handle.**

## A.4 Permission gates so Technical Sales can reach proposal creation

The proposal/funnel create flows are gated by role lists that currently exclude the technical roles:

- `sales_funnel/views.py` → `can_access_funnel`, `is_manager`, and the navbar Funnel gate.
- `sales_proposals/` create views + `templates/base.html` Proposals gate (`'salesperson,supervisor,teamlead,asm,avp,admin,president,gm,vp'`).

**Change:** add `technical_sales` (and `techmgr`/`asst_techmgr` for visibility) to:
- the Proposals navbar gate and the proposal create view's permission check,
- `can_access_funnel` / Funnel navbar gate,
- the "Add Entry"/create gates as appropriate.

## A.5 Funnels & proposals visible to Technical Manager / Assistant Technical Manager

This is the manager-visibility requirement. Using the `Team.tech_manager` link (manager → team) and the `Team.technical_sales` M2M (team → TS staff):

- **`visible_proposals_queryset(user)`** (`sales_proposals/views.py` ~line 444) — add branches:
  - `technical_sales` → `Proposal.objects.filter(created_by=user)` (their own).
  - `techmgr` / `asst_techmgr` → proposals whose `created_by` is a Technical Salesperson attached to a team this manager heads: `created_by__in=<TS users of user.tsg_managed_teams>`.
  - **Must be explicit** — the default for this helper is "see all."
- **`visible_funnel_entries(user)`** (`sales_funnel/views.py` ~line 147) — add the mirror branches scoped by `salesperson` (requires A.2 fix):
  - `technical_sales` → `filter(salesperson=user)`.
  - `techmgr` / `asst_techmgr` → `filter(salesperson__in=<TS users of their teams>)`.
  - **Must be explicit** — default is "see all."
- **`sales_monitoring`** dashboards — route `techmgr`/`asst_techmgr` to a team-scoped view of their Technical Sales staff (Phase 2 can add a dedicated Technical dashboard; Phase 1 can reuse the manager/team view).

## A.6 Approval chain for Technical Sales proposals

From the base plan Section 5.5, with the author now being `technical_sales`:

- `Proposal.get_approval_chain()` resolves the creator's group via `TeamMembership`; a `technical_sales` user won't have a regular `TeamMembership`, so add a resolution branch: for a `technical_sales` creator, resolve the approver as the **Technical Manager / Assistant Technical Manager of the team(s) they handle** (`Team.tech_manager`), instead of a sales supervisor.
- Add to `ROLE_LEVEL`: `technical_sales: 1` (peer of salesperson) and `techmgr`/`asst_techmgr` at a supervisor-equivalent level (e.g. `3`) so the Technical Manager outranks the TS author and is a valid approver.
- Confirm with management (Section 9, Q3) whether technical proposals need approval at all, or only above a ₱ threshold like regular proposals.

## A.7 Updated change checklist (additions to Section 7)

- [ ] `sales_funnel/models.py` — broaden `SalesFunnel.salesperson.limit_choices_to` to include `technical_sales` (**A.2**, migration)
- [ ] `sales_proposals/forms.py` — add `technical_sales` (+ `techmgr`/`asst_techmgr`) branch to `ProposalForm.__init__` customer scoping (**A.3a**)
- [ ] `sales_proposals/views.py` — proposal create view permission gate includes `technical_sales`; (optional) support `?customer=<id>` pre-select (**A.3**, **A.4**)
- [ ] `core/views.py` — confirm `global_search` customer results work for `technical_sales` once `visible_customers_queryset` has the branch (**A.3b**)
- [ ] `sales_funnel/views.py` — `can_access_funnel` + create gates include `technical_sales` (**A.4**)
- [ ] `visible_proposals_queryset` / `visible_funnel_entries` — explicit `technical_sales` + `techmgr`/`asst_techmgr` branches (**A.5**; also in Section 5)
- [ ] `Proposal.get_approval_chain()` — technical-author approver resolution via `Team.tech_manager` (**A.6**)
- [ ] `templates/base.html` — Proposals + Funnel nav gates include the technical roles (**A.4**)
- [ ] Tests — see A.9

## A.8 Additional open questions for management

7. **Create-proposal scope:** May Technical Sales create a proposal for **any** customer in the team(s) they handle (recommended), or only for customers explicitly linked to them?
8. **Auto-funnel ownership:** The auto-created funnel entry will be owned by the Technical Salesperson (via `salesperson`). Is that the desired reporting owner, or should it credit the original account manager? *(Affects A.2 and funnel/monitoring reports.)*
9. **Convenience deep-link:** Do you want a "Create Proposal" button on customer search results / customer detail that pre-selects the customer (A.3)? Yes/No.
10. **Manager edit rights:** Technical Manager/Assistant — **view only** on their TS staff's funnels/proposals (recommended), or also edit/approve?

## A.9 Additional tests (append to Section 10 plan)

- A `technical_sales` user attached to **Team A** can create a proposal for a Team A customer; a **linked funnel entry is auto-created** with the correct `customer`, `stage='quoted'`, and `salesperson=the TS user`.
- The same TS user **cannot** select/search a Team B customer in the proposal form (scoping), unless also attached to Team B.
- A single TS user attached to **both** teams can create proposals for customers of either team.
- A `techmgr`/`asst_techmgr` heading Team A **sees** the TS user's proposals and funnel entries; a manager of an unrelated team does **not**.
- Regression: a `technical_sales` user with **no** team attachment sees **no** customers/proposals/funnel entries (guards against the "see all" default).

## A.10 Effort delta

These additions are mostly new `if` branches in existing helpers/forms plus one `AlterField` migration and the approval-chain branch. Estimated **+1 to +1.5 dev-days** on top of Phase 1 (Section 11), including tests. No new models beyond the `Team.technical_sales` M2M already in the base plan.

---

# Addendum B — Management Decisions (Approved Answers) & Refined Design

**Status:** Decisions received from management — these resolve the open questions in Section 9 and Addendum A.8 and refine the design accordingly. Build still pending final go-ahead.

## B.1 Decisions

| # | Question | Decision |
|---|---|---|
| A.8-Q7 / S9-Q3 | Create-proposal scope | Technical Sales create proposals for **the team(s) they handle**. **Plus:** when there is only **one** Technical Sales person, an **admin checkbox** can grant that single TS person the **other team** as well (so one TS can cover both Team A and Team B). |
| A.8-Q8 | Auto-funnel ownership | The funnel/performance credit goes to the **Technical Salesperson who created the proposal**, **regardless of which salesperson owns/was assigned** the customer. |
| A.8-Q9 | Convenience deep-link | **Yes** — add a "Create Proposal" action from customer search results / customer detail that pre-selects the customer. |
| A.8-Q10 / S9-Q3 | Manager approval rights | Technical Manager / Assistant Technical Manager **must approve the proposal before it can be sent to the customer, regardless of price** (price-independent approval, to verify correctness). **Plus:** an **option to disable the approval requirement** for a Technical Salesperson once they have **mastered** proposal creation. |

## B.2 Design impact of each decision

### B.2.1 Create-proposal scope + "single-TS covers both teams" admin checkbox (Q7)

The base design already supports multi-team coverage via the `Team.technical_sales` M2M (a TS user attached to two teams sees both). The new requirement is an **explicit admin toggle** for the single-TS case rather than relying on manually attaching the same user to both teams. Recommended implementation:

- Add a boolean on the Technical Sales user's profile/assignment, e.g. **`handles_all_technical_teams`** (`BooleanField`, default `False`), editable by admin on the user-edit screen.
- Scoping precedence for a `technical_sales` user becomes:
  1. If `handles_all_technical_teams` is `True` → scope = **all teams that have a Technical Manager** (i.e., all technical-covered teams, effectively Team A + Team B).
  2. Else → scope = the teams in `user.ts_teams` (the `Team.technical_sales` M2M).
- This keeps the normal two-person split (each attached to their team) while giving admins a one-click way to let a lone TS cover everything, and to revert it when a second TS is hired.

> Both mechanisms coexist: the M2M handles explicit per-team assignment; the checkbox is the "cover all technical teams" shortcut. The scoping helpers (`visible_customers_queryset`, `visible_funnel_entries`, `visible_proposals_queryset`, and the `ProposalForm` customer branch) all read through a single new helper, e.g. `technical_sales_team_ids(user)`, that applies this precedence so the rule lives in exactly one place.

### B.2.2 Funnel credit to the Technical Sales creator (Q8)

Confirms and **hardens** the Addendum A.2 fix:

- `update_sales_funnel()` already sets `salesperson=proposal.created_by`, so the funnel entry is **already credited to the TS creator** — which is exactly what management wants, **independent of `Customer.salesperson`** (the customer's assigned owner).
- Required change remains: broaden `SalesFunnel.salesperson.limit_choices_to` to include `technical_sales` (A.2) so the credited owner is valid and the entry is picked up by the TS/Technical-Manager funnel scoping.
- **Reporting note:** because credit follows the creator, a Technical Sales proposal for a customer owned by (say) a Team A account manager will produce a funnel entry owned by the **TS person**, not the account manager. Confirm this is the intended effect on each account manager's own funnel/quota numbers (it means that deal does **not** appear under the account manager's funnel). This is consistent with "performance credited to Technical Sales," and is called out so Sales Monitoring reports are read correctly.

### B.2.3 Convenience deep-link (Q9)

- Add a **"Create Proposal"** button on:
  - the customer **search results** rows (navbar global search results page), and
  - the **customer detail** page,
  visible to roles allowed to create proposals for that customer (incl. `technical_sales`).
- The button links to the proposal create URL with the customer pre-selected, e.g. `…/proposals/create/?customer=<id>`.
- The proposal create view reads `?customer=<id>` and sets the form's initial customer **only if that customer is within the creator's allowed/scoped queryset** (re-validate server-side against the same scoped queryset used in `ProposalForm` — never trust the query param alone).

### B.2.4 Price-independent approval + per-TS "mastered" override (Q10)

This is the most significant logic change, because the current rule is **purely price-based**:

- Today: `calculate_totals()` sets `approval_required = (approval_total_php >= ₱500,000)` (`sales_proposals/models.py` ~line 257).
- New requirement for Technical Sales authors:
  1. **Always require approval regardless of price** (Technical Manager/Assistant verifies correctness before send), **unless**
  2. the TS author has been flagged as **"mastered"**, in which case approval is **not** required.

**Recommended implementation:**

- Add a boolean on the Technical Sales user, e.g. **`ts_approval_exempt`** (a.k.a. "mastered — proposals auto-approved / no approval needed"), default `False`, editable by admin / Technical Manager.
- In `calculate_totals()`, make the approval decision role-aware:
  ```python
  if self.created_by and self.created_by.role == 'technical_sales':
      self.approval_required = not getattr(self.created_by, 'ts_approval_exempt', False)
  else:
      self.approval_required = php_total >= Decimal('500000')   # existing rule
  ```
- In `get_approval_chain()`, add the technical branch (Addendum A.6): for a `technical_sales` creator, the approver is the **Technical Manager / Assistant Technical Manager** of the team(s) they handle (`Team.tech_manager`), **not** a sales supervisor/AVP. Price tiers (`ProposalApprovalTier`) are **bypassed** for TS authors — approval is required whenever `approval_required` is True (which is "always, unless exempt").
- The existing **send gate already enforces this**: `can_be_sent()`/send flow blocks sending while `approval_required and approval_status != 'approved'` (`sales_proposals/models.py` ~line 331). So "must be approved before sending to customer" needs **no new gate** — it falls out of setting `approval_required=True` for non-exempt TS proposals.
- When a TS user is later marked `ts_approval_exempt=True`, new proposals compute `approval_required=False`, skip the chain, and can be sent directly. `ensure_approval_chain()` already deletes steps and sets status to `not_required` when `approval_required` is False.

**Who may flip the "mastered" switch?** Recommend **admin and the Technical Manager/Assistant** (they supervise the TS person). Confirm (B.4-Q13).

## B.3 Updated data-model & checklist additions

| Model / field | Change | Migration |
|---|---|---|
| `users.User` (or TS profile) | `handles_all_technical_teams` boolean (B.2.1) | `AddField` |
| `users.User` (or TS profile) | `ts_approval_exempt` boolean — "mastered, no approval" (B.2.4) | `AddField` |
| `sales_funnel.SalesFunnel` | broaden `salesperson.limit_choices_to` to include `technical_sales` (B.2.2 / A.2) | `AlterField` (no-op at DB) |
| `teams.Team` | `technical_sales` M2M (from base plan Section 4.2) | `AddField` |

Checklist additions (extend Section 7 / A.7):

- [ ] `users/models.py` — add `handles_all_technical_teams` and `ts_approval_exempt` booleans (+ migration)
- [ ] `users/` admin/edit forms — expose both toggles to admin (and TM for the mastery flag)
- [ ] `teams/` (or `customers/permissions.py`) — `technical_sales_team_ids(user)` helper encoding the B.2.1 precedence (checkbox → all technical teams; else `ts_teams`)
- [ ] `sales_proposals/models.py` — role-aware `approval_required` in `calculate_totals()` (B.2.4)
- [ ] `sales_proposals/models.py` — `get_approval_chain()` technical branch via `Team.tech_manager`, bypassing price tiers for TS authors (B.2.4 / A.6)
- [ ] `sales_proposals/views.py` — proposal create view honors `?customer=<id>` pre-select, server-side re-validated against the scoped queryset (B.2.3)
- [ ] customer **search results** + **customer detail** templates — "Create Proposal" deep-link button (B.2.3)
- [ ] All scoping helpers + `ProposalForm` customer branch read through `technical_sales_team_ids(user)` (B.2.1)

## B.4 Remaining confirmations (small)

11. **Mastery scope:** Is `ts_approval_exempt` **per Technical Salesperson** (recommended), or should it be per team / global? *Recommended: per TS person.*
12. **Exempt = no approval vs. auto-approved:** When "mastered," should the proposal be **"not required"** (no approval step, cleanest) or recorded as **"auto-approved"** for audit trail? *Recommended: not required, with a change-log note.*
13. **Who sets the mastery flag:** Admin only, or **admin + Technical Manager/Assistant**? *Recommended: admin + Technical Manager/Assistant.*
14. **Deep-link visibility:** Should the "Create Proposal" button appear for **all** proposal-creating roles, or **only** Technical Sales (and managers)? *Recommended: all roles that can create a proposal for that customer, with per-row scoping.*

## B.5 Effort delta (on top of Addendum A)

- `handles_all_technical_teams` + `ts_approval_exempt` fields, the `technical_sales_team_ids` precedence helper, the role-aware approval logic, the technical approval-chain branch, the deep-link button, and tests for: single-TS-covers-both (checkbox on/off), funnel credited to TS creator, mastered-TS skips approval, non-mastered-TS always requires approval regardless of price, and manager visibility.
- Estimated **+1 to +2 dev-days** on top of Phase 1 + Addendum A.

## B.6 Net phased plan (consolidated)

**Phase 1 (MVP, now scoped by Addenda A & B):**
1. `technical_sales` role; `Team.technical_sales` M2M; `handles_all_technical_teams` + `ts_approval_exempt` user flags (migrations).
2. `technical_sales_team_ids(user)` helper (checkbox precedence) used by all scoping.
3. Customer visibility + `ProposalForm` customer scoping + navbar search for `technical_sales`, `techmgr`, `asst_techmgr`.
4. Proposal creation for TS → **auto-funnel entry credited to the TS creator** (broaden `SalesFunnel.salesperson`).
5. Price-independent approval for TS (Technical Manager/Assistant approves before send) **with** per-TS "mastered" exemption.
6. "Create Proposal" deep-link from search / customer detail (server-side re-validated).
7. Funnels + proposals visible to Technical Manager / Assistant (team-scoped).
8. Navbar gates; user-creation flows for TS/TM.
9. Full test suite (Addendum A.9 + B.5 cases).

**Phase 2 (optional, later):** offering-type classification (parts/services/repair/in-house/remote), dedicated Technical Sales + Technical Manager dashboards, optional `customer_service` ticket linkage.

**All decisions above are recorded for implementation upon final management approval. No code has been written yet.**
