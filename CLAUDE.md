# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MI CRM v2 is a Django-based Customer Relationship Management system for Micro Image International Corporation (Philippines). It is a server-rendered web app (Django templates + Bootstrap 5 + vanilla JS) with a REST API for a companion Android app.

## Commands

```bash
# Run development server
python manage.py runserver

# Create/apply migrations
python manage.py makemigrations
python manage.py migrate

# Run tests for a specific app
python manage.py test <app_name>

# Collect static files
python manage.py collectstatic --noinput

# Deploy to production
./deploy.sh              # interactive deploy via rsync + gunicorn restart
./deploy.sh --dry-run    # preview rsync without changes
```

Dependencies are in `dependencies/requirements.txt` (dev) and `dependencies/requirements-prod.txt` (prod). Install via `pip install -r dependencies/requirements.txt`.

## Architecture

### Apps

Each directory in the root is a Django app. The main apps are:

| App | Purpose |
|-----|---------|
| `core` | Home view, MFA middleware, site-wide settings (`SiteSetting` model) |
| `users` | Custom `User` model (AbstractUser + role field), login lockout, activity logging, MFA |
| `customers` | Customer database, duplicate detection, create-request approval workflow |
| `teams` | Three-tier hierarchy: `Team` (AVP-owned) → `Group` (Supervisor-owned) → `TeamMembership` |
| `sales_funnel` | 4-stage pipeline tracking (quoted → closable → project → services) |
| `sales_monitoring` | Activity logging (calls, meetings, tasks, emails, proposal activities) |
| `sales_proposals` | Proposal create/approve/PDF export; multi-tier approval chain |
| `lead_generation` | Lead scoring engine (`scoring_engine.py`, `scoring_models.py`), lead-to-customer conversion |
| `file_sharing` | Document library by category with access logging |
| `gamification` | Points, levels, badges, daily/weekly missions |
| `mass_mailing` | Email campaign manager with recipient tracking |
| `customer_service` | Ticketing with Redmine integration |
| `warehouse` | Delivery itinerary board (For Schedule / Scheduled / Accomplished + VAN DETAILS), real-time WebSocket feed (Django Channels), Excel export, delivery history/backlog tracing |
| `crm_project` | Django project config, main URL router, shared DRF serializers and API views |

### Role-Based Access Control

15 roles defined in `users/models.py`: `admin`, `avp`, `supervisor`, `salesperson`, `vp`, `gm`, `president`, `asm`, `sm`, `teamlead`, `techmgr`, `asst_techmgr`, `technical_sales`, `marketing`, `warehouse`.

Visibility scoping helpers live in `crm_project/serializers.py`:
- `get_visible_customer_queryset(user)`
- `get_visible_proposal_queryset(user)`
- `get_visible_activity_queryset(user)`

These filter querysets based on role — use them rather than re-implementing role logic.

### Authentication

- Login: email or username via `django-allauth`; MFA/TOTP enforced by `core/middleware.py` (`MFARequiredMiddleware`) when `SiteSetting.mfa_required = True`
- Brute-force lockout: `users/backends.py` (`LockoutAwareBackend`) — locks account after N failures, logs to `FailedLoginAttempt`
- API auth: DRF Token Auth (`/api/v1/api-token-auth/`)

### REST API

DRF `DefaultRouter` mounted at `/api/v1/`. ViewSets are defined in `crm_project/api_views.py` (except `UserViewSet` which is in `users/api.py`). Endpoints: `users`, `customers`, `customer-requests`, `funnel`, `proposals`, `activities`, `campaigns`.

### Database

Configured via env vars. Dev defaults to SQLite; production uses MariaDB (`DB_ENGINE=mariadb`). All models use `Meta.indexes` for performance-critical fields. Copy `.env.example` to `.env` and fill in values before running.

### PDF Generation

Proposals export to PDF using `reportlab`. PDF logic lives in `sales_proposals/` — look for views that return `HttpResponse` with `content_type='application/pdf'`.

### Deployment

`deploy.sh` rsyncs the working tree to `crm_azure:/var/www/mi_crm`, then runs migrations and restarts gunicorn. Production `.env` is never overwritten (excluded from rsync). SSH key at `~/.susi/CRM_key.pem`.

## Key Conventions

- **No hard deletes** — use `is_active = False` flags for users and customers.
- **Approval chains** are dynamic: proposal approval steps are stored as `ProposalApprovalStep` rows, not hardcoded logic.
- **Audit logging** — every significant action (login, password reset, profile change) is logged. Add to existing log models rather than print/logging to console.
- **Templates** are in the root `templates/` directory (not per-app), organized by app name subdirectory.
- **No frontend build step** — Bootstrap 5 and JS are loaded from CDN or `static/`. There is no npm/webpack.

## Documentation

Detailed feature docs are in `docs/`. Key references:
- `docs/HANDOVER_GUIDE.md` — comprehensive developer onboarding
- `docs/TEAMS_APP.md` — role/permission matrix for team hierarchy
- `docs/SALES_PROPOSALS_DOCUMENTATION.md` — proposal lifecycle and approval chain
- `docs/WAREHOUSE_APP.md` — delivery itinerary board, WebSocket feed, warehouse role & export rules
- `docs/LEAD_GENERATION_GUIDE.md` — lead scoring engine details
- `docs/PRODUCTION_DEPLOY.md` — server setup (gunicorn, systemd, nginx)
