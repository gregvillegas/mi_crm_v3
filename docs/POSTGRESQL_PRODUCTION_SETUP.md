# PostgreSQL Production Setup Guide

This guide explains the recommended PostgreSQL production setup for the Micro Image CRM and how to migrate from SQLite to PostgreSQL while keeping only the core setup data you still need.

## Recommended Production Database

Use **PostgreSQL 15 or 16** for production.

Why PostgreSQL is the recommended choice for this CRM:

- Better multi-user concurrency than SQLite
- Strong transaction support for customer updates, proposals, approvals, and mass mailing
- Better long-term scalability for CRM data, logs, and reporting
- Excellent Django compatibility
- Mature backup and restore tooling

## Django Production Database Settings

The project now supports environment-based database settings in `crm_project/settings.py`.

### Environment Variables

Set these values in your production environment:

```bash
export DB_ENGINE=postgresql
export DB_NAME=mi_crm
export DB_USER=mi_crm_user
export DB_PASSWORD='replace_with_secure_password'
export DB_HOST=127.0.0.1
export DB_PORT=5432
export DB_CONN_MAX_AGE=60
export DB_SSLMODE=prefer
```

### Django Behavior

- If `DB_ENGINE=postgresql`, Django uses PostgreSQL.
- If `DB_ENGINE` is not set, the project falls back to SQLite for development.

## Python Dependency

Production dependency now uses Psycopg 3:

```txt
psycopg[binary]==3.2.9
```

Install production dependencies with:

```bash
pip install -r dependencies/requirements-prod.txt
```

## Create PostgreSQL Database and User

Login to PostgreSQL:

```bash
sudo -u postgres psql
```

Run:

```sql
CREATE DATABASE mi_crm ENCODING 'UTF8';
CREATE USER mi_crm_user WITH PASSWORD 'replace_with_secure_password';
ALTER ROLE mi_crm_user SET client_encoding TO 'utf8';
ALTER ROLE mi_crm_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE mi_crm_user SET timezone TO 'Asia/Manila';
GRANT ALL PRIVILEGES ON DATABASE mi_crm TO mi_crm_user;
```

If needed, allow schema ownership after the first login:

```sql
\c mi_crm
GRANT ALL ON SCHEMA public TO mi_crm_user;
ALTER SCHEMA public OWNER TO mi_crm_user;
```

## What Data To Keep

Based on your requirement, the recommended migration keeps:

- `users`
- `teams`
- `lead source types`
- `quotas`

Recommended to keep as well:

- `auth.group`

Reason:

- Keeping `users` alone may lose team/group relationships used by dashboards, approvals, and role visibility.
- `teams` preserves team/group/team-membership structure.
- `lead_generation.LeadSource` preserves lead source configuration.
- `teams.TeamMembership` preserves salesperson quota values stored at membership level.
- Additional quota and target tables preserve monthly commitments and executive targets.
- `auth.group` is safe to include if you use Django auth group assignments.

## What To Leave Fresh

Since you want to start customer data from scratch, do **not** migrate these business datasets:

- `customers`
- `sales_funnel`
- `sales_proposals`
- `mass_mailing`
- `customer_service`
- historical activity/points if you want a clean production start

This produces a cleaner production go-live with only users and configuration retained.

## Quota-Related Models To Keep

If you want quotas in production, include these models:

- `teams.TeamMembership`
- `teams.SupervisorCommitment`
- `teams.SupervisorCommitmentLog`
- `teams.PersonalContribution`
- `teams.AsmPersonalTarget`
- `teams.RoleMonthlyQuota`
- `teams.CompanyAnnualTarget`
- `teams.CompanyAnnualTargetLog`

## Step 1: Create a Selective SQLite Export

From your current SQLite-based project:

```bash
python manage.py dumpdata \
  users.User \
  teams.Team \
  teams.Group \
  teams.TeamMembership \
  teams.SupervisorCommitment \
  teams.SupervisorCommitmentLog \
  teams.PersonalContribution \
  teams.AsmPersonalTarget \
  teams.RoleMonthlyQuota \
  teams.CompanyAnnualTarget \
  teams.CompanyAnnualTargetLog \
  auth.Group \
  lead_generation.LeadSource \
  --exclude auth.permission \
  --exclude contenttypes \
  --indent 2 > seed_core_data.json
```

This export keeps users, team structure, lead sources, and quota-related records while leaving customer and transactional data fresh.

## Step 2: Point Django To PostgreSQL

In the production server shell:

```bash
export DB_ENGINE=postgresql
export DB_NAME=mi_crm
export DB_USER=mi_crm_user
export DB_PASSWORD='replace_with_secure_password'
export DB_HOST=127.0.0.1
export DB_PORT=5432
export DB_CONN_MAX_AGE=60
export DB_SSLMODE=prefer
```

## Step 3: Run Fresh Migrations On PostgreSQL

```bash
python manage.py migrate
```

This creates all tables in PostgreSQL with no customer data yet.

## Step 4: Load Only the Saved Core Data

```bash
python manage.py loaddata seed_core_data.json
```

## Step 5: Reset PostgreSQL Sequences

After `loaddata`, reset sequences so new records continue from the correct ID values:

```bash
python manage.py sqlsequencereset users teams lead_generation auth | python manage.py dbshell
```

If you did not import `auth.Group`, you can remove `auth` from the command.

## Step 6: Verify Required Data

Run a quick shell check:

```bash
python manage.py shell
```

Then:

```python
from users.models import User
from lead_generation.models import LeadSource
from teams.models import Team, Group, TeamMembership

print("Users:", User.objects.count())
print("Lead Sources:", LeadSource.objects.count())
print("Teams:", Team.objects.count())
print("Groups:", Group.objects.count())
print("Memberships:", TeamMembership.objects.count())
```

To verify quotas too:

```python
from teams.models import (
    SupervisorCommitment, SupervisorCommitmentLog, PersonalContribution,
    AsmPersonalTarget, RoleMonthlyQuota, CompanyAnnualTarget, CompanyAnnualTargetLog
)

print("Supervisor Commitments:", SupervisorCommitment.objects.count())
print("Commitment Logs:", SupervisorCommitmentLog.objects.count())
print("Personal Contributions:", PersonalContribution.objects.count())
print("ASM Targets:", AsmPersonalTarget.objects.count())
print("Role Monthly Quotas:", RoleMonthlyQuota.objects.count())
print("Company Annual Targets:", CompanyAnnualTarget.objects.count())
print("Company Annual Target Logs:", CompanyAnnualTargetLog.objects.count())
```

## Step 7: Create Fresh Customer Data

Since customers will start fresh:

- keep the PostgreSQL database with empty `customers` tables
- import customers later using your preferred clean import process
- rebuild new proposals, funnel entries, and campaign recipients only after customers are loaded

## Environment Variables (Gunicorn / systemd)

The project reads its configuration from `/var/www/mi_crm/.env` (via `python-decouple`), so the recommended approach is to put the PostgreSQL settings there — no web-server-specific configuration is needed:

```ini
DB_ENGINE=postgresql
DB_NAME=mi_crm
DB_USER=mi_crm_user
DB_PASSWORD=replace_with_secure_password
DB_HOST=127.0.0.1
DB_PORT=5432
DB_CONN_MAX_AGE=60
DB_SSLMODE=prefer
```

`.env` is read by both the Gunicorn (WSGI) and Daphne (ASGI) processes as long as their systemd unit uses `WorkingDirectory=/var/www/mi_crm`. If you prefer to keep secrets out of `.env`, pass them instead via the `Environment=` / `EnvironmentFile=` directives in the `gunicorn.service` and `mi_crm_daphne.service` units (see `PRODUCTION_DEPLOY.md`).

## Recommended Production Checklist

- Set `DEBUG=False`
- Restrict `ALLOWED_HOSTS`
- Move `SECRET_KEY` to environment variables
- Move email passwords and Redmine credentials to environment variables
- Use PostgreSQL backups:
  - daily `pg_dump`
  - periodic full server backups
- Run:

```bash
python manage.py collectstatic --noinput
```

## Recommended Go-Live Order

1. Set up PostgreSQL
2. Configure production environment variables
3. Run migrations on PostgreSQL
4. Load `seed_core_data.json`
5. Reset sequences
6. Verify users, teams, and lead sources
7. Import fresh customer data
8. Test login, dashboards, proposals, and mass mailing
9. Switch production traffic

## Notes

- The old helper script `prepare_production.py` is still MySQL-oriented and should not be used as-is for PostgreSQL deployment.
- For this CRM, a selective fixture import is better than a full database migration because you want a clean production start for customers and transactional modules.
