# Customer Status Sync — Auto-Inactive After 3 Months (and Millionaire Flag)

**Command:** `python manage.py sync_customer_status_flags`
**File:** `customers/management/commands/sync_customer_status_flags.py`
**Audience:** admins / whoever maintains the production server.

This documents the system-managed customer status flags — in particular the rule
that **a customer with no sales activity for the past 3 months (90 days) is
marked inactive** — and how to schedule the job on the server.

---

## 1. What the rule is

A customer is flagged **auto-inactive** when their most recent *reference date*
is **older than 90 days** (3 months). This sets `Customer.auto_inactive_flag =
True`; the customer is then treated as inactive across the app
(`is_effectively_active = is_active AND NOT auto_inactive_flag`).

The **reference date** is the newest of, in order of preference:
1. the customer's last **sales activity** creation date, else
2. the last time the customer was **assigned / reassigned** a salesperson
   (from `CustomerHistory`), else
3. the customer's **created** date.

So a brand-new customer with no activity yet is judged from when they were
created or assigned — they aren't flagged inactive on day one, only once 90 days
pass with nothing happening.

The 90-day window is defined in the command as:

```python
inactivity_cutoff = now - timedelta(days=90)
auto_inactive_flag = bool(reference_dt and reference_dt <= inactivity_cutoff)
```

> To change the period (e.g. 60 or 120 days), edit `timedelta(days=90)` in
> `sync_customer_status_flags.py`. It is not yet a settings value.

## 2. What else the same command maintains

The one command keeps four system-managed fields in sync (all on `Customer`):

| Field | Meaning | Rule |
|---|---|---|
| `last_sales_activity_at` | Newest sales-activity date | Max `SalesActivity.created_at` for the customer |
| `auto_inactive_flag` | Inactive by inactivity | reference date ≤ now − 90 days |
| `lifetime_won_revenue` | Cumulative won SRP | Sum of `retail` on won funnel entries |
| `is_millionaire_account` | "Millionaire" badge | lifetime won revenue > ₱1,000,000 |

Every change is written with a `CustomerHistory` audit row
(`action='field_updated'`, `user_agent='system/sync_customer_status_flags'`), so
you can see when and why a customer flipped inactive or became a millionaire
account.

## 3. How a customer gets re-activated

Reactivation is **automatic and immediate** — it does *not* wait for this job.
When a sales activity is logged for a customer that is inactive or auto-inactive,
the app clears the flags right away:

- Web: `sales_monitoring/views.py` (on activity create/complete).
- Mobile API: `crm_project/serializers.py` (on activity create).

Both set `is_active=True` and `auto_inactive_flag=False` the moment an activity
is recorded. The next scheduled sync then recomputes everything consistently
from the data.

## 4. Running the command

```bash
# Preview — shows what would change, writes nothing
python manage.py sync_customer_status_flags --dry-run

# Apply to all customers
python manage.py sync_customer_status_flags

# Sync a single customer (handy for spot-checking)
python manage.py sync_customer_status_flags --customer-id 123
```

The command is **idempotent** — it only writes rows whose computed values differ
from what's stored, and logs an audit entry per change. Running it repeatedly is
safe.

## 5. Production scheduling (cron)

This job is **not scheduled automatically** inside the app and is **not** part of
`deploy2.sh`. On the production server it must be run by cron. A **daily** run is
appropriate (the 90-day boundary moves one day at a time, so once a day is
plenty).

### 5.1 Edit the crontab
Log in as the user that runs the Django app (e.g. `www-data`, `ubuntu`, or your
deploy user) and open the crontab:

```bash
crontab -e
```

### 5.2 Add the cron entry
Adjust the paths to match your deployment (these match the layout used in the
other maintenance docs: app at `/private/var/www/mi_crm`, venv at
`/private/var/www/mi_crm/venv`):

```text
# Sync customer status flags (auto-inactive after 90 days, millionaire flag) — daily at 1:30 AM
30 1 * * * cd /private/var/www/mi_crm && /private/var/www/mi_crm/venv/bin/python manage.py sync_customer_status_flags >> /private/var/www/mi_crm/logs/customer_status_sync.log 2>&1
```

Make sure the log directory exists:

```bash
mkdir -p /private/var/www/mi_crm/logs
```

### 5.3 Verify it's scheduled

```bash
crontab -l | grep sync_customer_status_flags      # confirm the entry is present
tail -n 20 /private/var/www/mi_crm/logs/customer_status_sync.log   # check last run output
```

Each run prints a one-line summary, e.g.
`Processed 1666 customers; updated 12.`

> **First deploy of this schedule:** run it once by hand (ideally with
> `--dry-run` first) so the initial back-fill of flags happens immediately rather
> than waiting for the next cron tick. On a large customer base the first full
> run touches many rows; subsequent daily runs change only a handful.

### 5.4 Timing note
Schedule it to run **before** any report that depends on the flags (e.g. the
dashboard "needs attention" count, which reads `auto_inactive_flag`). An early-
morning run (1:30 AM here) means the numbers are fresh for the business day.

---

## 6. Where the flags are used

- **Customer list** filter: Active / Inactive uses
  `is_active & auto_inactive_flag` (`customers/views.py`).
- **Dashboard**: the "needs attention" count = `customers.filter(auto_inactive_flag=True)`
  (`crm_project/api_views.py`).
- **Display status**: `Customer.display_status` / `is_effectively_active`
  surface "Millionaire Active/Inactive" and plain Active/Inactive labels.

---

## 7. Files involved

| File | Role |
|---|---|
| `customers/management/commands/sync_customer_status_flags.py` | The job itself |
| `customers/models.py` | `auto_inactive_flag`, `last_sales_activity_at`, `lifetime_won_revenue`, `is_millionaire_account`, `status_last_synced_at` + `is_effectively_active`/`display_status` |
| `sales_monitoring/views.py`, `crm_project/serializers.py` | Immediate re-activation when an activity is logged |
| `customers/models.py` → `CustomerHistory` | Audit trail of each flag change |
