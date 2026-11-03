# MiCRM — Project Handover Guide

**Prepared for:** Sr. Teamlead / Teamlead  
**Company:** Micro Image International Corp.  
**Production Target:** Ubuntu 22.04 LTS · nginx · Gunicorn (WSGI) · Daphne (ASGI) · Redis · MariaDB 10.6  
**Date:** July 2026

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Project Structure](#2-project-structure)
3. [User Roles & Access Levels](#3-user-roles--access-levels)
4. [Application Modules](#4-application-modules)
5. [Key Configuration Files](#5-key-configuration-files)
6. [Environment Variables Reference](#6-environment-variables-reference)
7. [Development Setup (Local Machine)](#7-development-setup-local-machine)
8. [Database: Backing Up Seed Data](#8-database-backing-up-seed-data)
9. [Production Deployment — Step by Step](#9-production-deployment--step-by-step)
10. [Post-Deployment Checklist](#10-post-deployment-checklist)
11. [Updating the Production Server](#11-updating-the-production-server)
12. [Admin Panel](#12-admin-panel)
13. [Routine Maintenance](#13-routine-maintenance)
14. [Troubleshooting Reference](#14-troubleshooting-reference)
15. [Important Credentials & Contacts](#15-important-credentials--contacts)

---

## 1. System Overview

MiCRM is a **Django 5.2** web application — a full-featured internal CRM built for Micro Image International Corp.'s sales organization. It manages the complete sales lifecycle from lead generation to customer service.

**Technology Stack**

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| Web Framework | Django 5.2.5 |
| Database (Production) | MariaDB 10.6 (on Ubuntu 22.04) |
| Database (Development) | SQLite 3 |
| Web Server | nginx (TLS, static/media, reverse proxy) |
| App Server (WSGI) | Gunicorn (systemd service `gunicorn`, unix socket `/run/gunicorn.sock`) |
| App Server (ASGI) | Daphne (systemd service `mi_crm_daphne`) — WebSocket feed |
| Channel Layer | Redis |
| Auth / MFA | django-allauth + TOTP |
| REST API | Django REST Framework |
| Frontend | Bootstrap 5 + Django templates |
| PDF Generation | ReportLab |
| Excel Export | openpyxl |

**Server Details**

| Item | Value |
|---|---|
| OS | Ubuntu 22.04 LTS |
| Domain | `micrm.microimageph.com` |
| Project path | `/var/www/mi_crm` |
| Python venv | `/var/www/mi_crm/venv` |
| nginx site config | `/etc/nginx/sites-available/micrm_nginx` |
| nginx error log | `/var/log/nginx/error.log` |
| nginx access log | `/var/log/nginx/access.log` |
| Gunicorn service | `systemctl status gunicorn` |
| Daphne service | `systemctl status mi_crm_daphne` |
| MariaDB database | `mi_crm` |
| MariaDB user | `mi_crm_user` |

---

## 2. Project Structure

```
mi_crm/
├── crm_project/            # Django project config
│   ├── settings.py         # All settings (reads from .env)
│   ├── urls.py             # Root URL configuration
│   ├── wsgi.py             # WSGI entry point for Gunicorn
│   ├── asgi.py             # ASGI entry point for Daphne (HTTP + WebSocket)
│   └── api_views.py        # REST API viewsets
│
├── core/                   # Shared utilities, base templates, middleware
│   └── management/
│       └── commands/
│           └── backup_seed_data.py   # Custom backup command
│
├── users/                  # Custom user model, roles, auth
├── customers/              # Customer records, contacts, delinquency
├── teams/                  # Teams, groups, memberships, quotas
├── sales_funnel/           # Sales pipeline management
├── sales_monitoring/       # Activity tracking, dashboards
├── sales_proposals/        # Proposal creation, PDF, approval workflow
├── lead_generation/        # Lead tracking, sources, scoring
├── file_sharing/           # Group file uploads and downloads
├── gamification/           # Leaderboard, badges, missions
├── mass_mailing/           # Email campaign builder
├── customer_service/       # Redmine-integrated support tickets
├── warehouse/              # Delivery itinerary board (Channels WebSocket, Excel export, history)
│
├── templates/              # All HTML templates
├── static/                 # Source static files (CSS, JS, images)
├── staticfiles/            # Collected static files (generated, do not edit)
├── media/                  # User-uploaded files
│
├── requirements.txt        # Pinned Python dependencies (see also dependencies/)
├── manage.py               # Django management script
├── deploy_crm_office.sh    # rsync + migrate + collectstatic (staging/office server)
├── deploy_crm_azure.sh     # rsync + migrate + collectstatic (production server)
├── etc/
│   └── micrm_nginx         # nginx site configuration
├── .env.example            # Environment variables template
├── .env                    # LIVE environment variables (never commit)
└── .gitignore
```

---

## 3. User Roles & Access Levels

The system uses a custom `role` field on the User model. Each role has different access within the dashboards and features.

| Role Code | Display Name | Typical Access |
|---|---|---|
| `admin` | Admin | Full access, all settings and management |
| `president` | President | Executive dashboard, read-all |
| `vp` | Vice President | Executive dashboard, read-all |
| `gm` | General Manager | Executive dashboard, read-all |
| `avp` | AVP | Team-level management, group oversight |
| `asm` | ASM | Group management, acting supervisor duties |
| `sm` | Sales Manager | Sales monitoring, team performance |
| `supervisor` | Supervisor | Group members' activities and proposals |
| `teamlead` | Teamlead | Group activities, own reporting |
| `salesperson` | Salesperson | Own customers, funnel entries, proposals |
| `marketing` | Marketing | Mass mailing, lead sources, campaigns |
| `techmgr` | Technical Manager | TSG group management |
| `asst_techmgr` | Asst. Technical Manager | TSG group support |
| `technical_sales` | Technical Sales | TSG customers/funnel/proposals in their covered teams |
| `warehouse` | Warehouse | Delivery itinerary board only (add/update deliveries; soft-locked to the warehouse app) |

**MFA (Two-Factor Authentication)** is enabled for all users via TOTP (Time-based One-Time Password using apps like Google Authenticator or Authy).

---

## 4. Application Modules

### Customers (`/customers/`)
- Full customer database with contact persons, industry, territory
- Transfer ownership between salespersons
- Delinquency tracking (import/export via CSV)
- Customer creation requests (requires approval from supervisors)
- Customer notes and activity history
- Backup and restore individual customer records
- Export to Excel

### Teams & Groups (`/teams/`)
- Hierarchical structure: **Team → Group → Members**
- Two group types: **Regular** (has supervisor) and **TSG** (Technical Sales Group, managed by Technical Manager)
- Team membership and quota assignment
- Monthly supervisor commitments and personal contribution tracking
- Company annual target management

### Sales Funnel (`/funnel/`)
- Kanban-style pipeline with stages (Quoted, Negotiation, Won, Lost, etc.)
- Entry management with cost and retail values
- Deal history and fiscal summary exports (Excel + PDF)
- Import from CSV

### Sales Monitoring (`/sales-monitoring/`)
- Role-specific dashboards:
  - **Salesperson** — own activity log
  - **Supervisor** — group members' activities
  - **AVP / Executive** — team and company-wide views
- Activity creation (calls, meetings, POCs)
- Group and team performance reports with fiscal summary
- Export to Excel and PDF

### Sales Proposals (`/proposals/`)
- Full proposal creation with line items
- Multi-tier approval workflow (configurable thresholds)
- PDF generation and email sending directly from the system
- Approval inbox for designated approvers

### Lead Generation (`/leads/`)
- Lead capture with scoring (0–100 automated scoring)
- Lead sources management
- Status workflow: New → Contacted → Qualified → Proposal Sent → Converted / Lost
- Convert leads directly to customers with optional funnel entry creation
- Analytics dashboard with conversion rates

### File Sharing (`/files/`)
- Upload files per sales group
- Role-based access (members see their group's files)
- In-browser file viewer for common formats
- Download tracking

### Gamification (`/gamification/`)
- Leaderboard based on sales activity
- Badges for achievements
- Mission creation and tracking

### Mass Mailing (`/mass-mailing/`)
- Email campaign builder
- Media library for reusable assets
- Send to customer lists
- Unsubscribe link auto-generated per recipient

### Customer Service (`/service/`)
- Integrated with Redmine ticketing system
- Create support tickets directly from a customer's profile
- Ticket status sync from Redmine

### Warehouse Deliveries (`/warehouse/`)
- Daily delivery itinerary board: **For Schedule**, **Scheduled Delivery**, **Accomplished Delivery**, and a **VAN DETAILS** footer (grouped by vehicle plate + driver)
- Real-time updates over WebSocket (Django Channels) — changes appear on every open board without a refresh
- **Warehouse** role adds/updates deliveries; the role is soft-locked to this module
- **Delivery History** page (date, status, company, item, AE, driver, warehouse staff) with **backlog tracing**
- Excel export (one sheet per section) — available to all viewers except the Account Manager (salesperson) role
- Managed in Django admin: `WarehouseStaff` (dropdown list, no login) and `Delivery` (inline status/driver/plate editing)
- One-off legacy seed: `python manage.py import_warehouse_itinerary`

### REST API (`/api/v1/`)
- Token-based authentication
- Endpoints: `users`, `customers`, `customer-requests`, `funnel`, `proposals`, `activities`, `campaigns`
- Primarily used by the MiCRM Android companion app

---

## 5. Key Configuration Files

### `.env` — Environment Variables
**Location on server:** `/var/www/mi_crm/.env`  
**Never commit this file.** It holds all secrets (database password, email password, secret key). See Section 6 for the full reference.

### `crm_project/settings.py`
All settings are read from `.env` via `python-decouple`. No hardcoded secrets. Key behaviours:
- `DEBUG=False` → enables production security headers (HSTS, secure cookies, SSL redirect)
- `DB_ENGINE=mariadb` → connects to MariaDB
- `DB_ENGINE=sqlite3` (or unset) → falls back to local SQLite for development
- Email falls back to file-based backend if `EMAIL_HOST_USER` is empty

### `etc/micrm_nginx`
**Deployed to:** `/etc/nginx/sites-available/micrm_nginx`  
Contains:
- A `default_server` block that uses `ssl_reject_handshake on;` to drop unknown hostnames
- Port 80 → `server` block that redirects everything to HTTPS
- Port 443 → `server` block with TLS, security headers, `client_max_body_size 150M`,
  static/media aliases, a private-network-restricted `/admin`, `proxy_pass` to the
  Gunicorn unix socket for `location /`, and a `location /ws/` proxy to Daphne for
  the Warehouse Deliveries WebSocket feed

### `deploy_crm_office.sh` / `deploy_crm_azure.sh`

rsync the working tree to the server, then run `migrate`, `collectstatic`, and
restart the `gunicorn` service. `.env`, `venv`, `media`, and `db.sqlite3` are
excluded so the server keeps its own secrets and data. Both support `--dry-run`.

> Deployment is not complete until **`mi_crm_daphne`** (the WebSocket/ASGI
> service) is restarted too — see
> [PRODUCTION_DEPLOY.md §8](PRODUCTION_DEPLOY.md#8-real-time-websockets-daphne--redis).

---

## 6. Environment Variables Reference

All variables go into `/var/www/mi_crm/.env` on the production server.

| Variable | Required | Example / Default | Description |
|---|---|---|---|
| `SECRET_KEY` | **Yes** | *(generated)* | Django secret key — must be unique and secret |
| `DEBUG` | **Yes** | `False` | Must be `False` in production |
| `ALLOWED_HOSTS` | **Yes** | `micrm.microimageph.com` | Comma-separated allowed hostnames |
| `DB_ENGINE` | **Yes** | `mariadb` | Use `mariadb` for production |
| `DB_NAME` | **Yes** | `mi_crm` | MariaDB database name |
| `DB_USER` | **Yes** | `mi_crm_user` | MariaDB username |
| `DB_PASSWORD` | **Yes** | *(your password)* | MariaDB password |
| `DB_HOST` | No | `127.0.0.1` | MariaDB host |
| `DB_PORT` | No | `3306` | MariaDB port |
| `EMAIL_HOST` | No | `email.microimageph.com` | SMTP server hostname |
| `EMAIL_PORT` | No | `587` | SMTP port |
| `EMAIL_USE_TLS` | No | `True` | Use TLS for SMTP |
| `EMAIL_HOST_USER` | **Yes** | `crm_sales@microimageph.com` | SMTP login user |
| `EMAIL_HOST_PASSWORD` | **Yes** | *(your password)* | SMTP password |
| `DEFAULT_FROM_EMAIL` | No | `sales@microimageph.com` | From address for outgoing email |
| `CORS_ALLOW_ALL_ORIGINS` | No | `False` | Set `False` in production |
| `CORS_ALLOWED_ORIGINS` | No | `https://micrm.microimageph.com` | Comma-separated CORS origins |
| `REDMINE_URL` | No | `http://10.30.30.131` | Redmine server URL |
| `REDMINE_API_KEY` | No | *(api key)* | Redmine API key for ticket creation |
| `REDMINE_PROJECT_ID` | No | `14` | Redmine project ID |
| `REDMINE_TRACKER_ID` | No | `7` | Redmine tracker ID |
| `SITE_URL` | **Yes** | `https://micrm.microimageph.com` | **CRITICAL:** Full URL for email links (unsubscribe, interested). Without this, campaign email links will be broken! |
| `SECURE_SSL_REDIRECT` | No | `True` | Force HTTPS redirect |
| `REDIS_URL` | **Yes** (prod) | `redis://127.0.0.1:6379/0` | Redis channel layer for the Channels WebSocket feed. Blank ⇒ in-memory layer (single-process dev only) |

**Generating a new SECRET_KEY:**
```bash
source /var/www/mi_crm/venv/bin/activate
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## 7. Development Setup (Local Machine)

Use this when making code changes locally before pushing to the server.

```bash
# 1. Clone or copy the project
cd /path/to/mi_crm

# 2. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate      # macOS / Linux
# venv\Scripts\activate       # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create local .env
cp .env.example .env
# Edit .env: set DEBUG=True, DB_ENGINE=sqlite3, leave EMAIL_HOST_USER blank

# 5. Run migrations
python manage.py migrate

# 6. Create a local admin user
python manage.py createsuperuser

# 7. Start the development server
python manage.py runserver
# Visit: http://127.0.0.1:8000
```

---

## 8. Database: Backing Up Seed Data

Before deploying to a fresh production server, export only the essential organizational data — users, teams, groups, and lead sources. This leaves all transactional data (customers, proposals, activities) behind for a clean production start.

### Run the backup command

```bash
cd /path/to/mi_crm
source venv/bin/activate

python manage.py backup_seed_data
```

**What gets exported:**

| Data | Why |
|---|---|
| Django `auth.Group` | Permission groups |
| `users.User` (all 87 users) | All CRM user accounts and roles |
| `teams.Team` | Sales team structure |
| `teams.Group` | Sales groups within teams |
| `teams.TeamMembership` | Which user belongs to which group |
| `lead_generation.LeadSource` | Lead source definitions |

**Output:** A file named `seed_backup_YYYY-MM-DD_HHMMSS.json` in the project root.

### Options

```bash
# Custom output path
python manage.py backup_seed_data --output /path/to/my_seed.json

# Exclude lead sources (only users + org structure)
python manage.py backup_seed_data --exclude-lead-sources

# Print to stdout
python manage.py backup_seed_data --stdout
```

> The backup file is excluded from git (`.gitignore`). Transfer it to the server manually via `scp`.

---

## 9. Production Deployment — Step by Step

> Follow these steps **in order**. Each step depends on the previous one.

---

### Step 1 — Create the seed backup (on your local machine)

```bash
cd /path/to/mi_crm
source venv/bin/activate
python manage.py backup_seed_data
# Note the filename: e.g., seed_backup_2026-07-22_174119.json
```

---

### Step 2 — Copy project files to the server

Run from your local machine:

```bash
rsync -avz --progress \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='venv' \
  --exclude='db.sqlite3' \
  --exclude='staticfiles' \
  --exclude='media' \
  /path/to/mi_crm/ \
  your_user@SERVER_IP:/var/www/mi_crm/

# Copy the seed backup file
scp seed_backup_2026-07-22_174119.json your_user@SERVER_IP:/var/www/mi_crm/
```

Replace `your_user` and `SERVER_IP` with the actual SSH user and server IP address.

---

### Step 3 — Install system packages (on the server)

SSH into the server, then run:

```bash
sudo apt-get update && sudo apt-get upgrade -y

sudo apt-get install -y \
    python3 python3-pip python3-venv python3-dev \
    nginx \
    mariadb-server mariadb-client \
    libmariadb-dev pkg-config \
    redis-server \
    git curl ufw \
    certbot python3-certbot-nginx
```

---

### Step 4 — Secure MariaDB and create the database

```bash
# Interactive security wizard — answer Yes to all prompts, set a root password
sudo mysql_secure_installation

# Log in to MariaDB as root
sudo mysql -u root -p
```

Inside the MariaDB shell:

```sql
CREATE DATABASE mi_crm CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'mi_crm_user'@'localhost' IDENTIFIED BY 'YOUR_STRONG_PASSWORD';
GRANT ALL PRIVILEGES ON mi_crm.* TO 'mi_crm_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

> Replace `YOUR_STRONG_PASSWORD` with a real strong password. You will use this in the `.env` file.

---

### Step 5 — Set up the Python virtual environment

```bash
cd /var/www/mi_crm

python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip wheel
pip install -r dependencies/requirements.txt
```

---

### Step 6 — Create and configure the `.env` file

```bash
cp /var/www/mi_crm/.env.example /var/www/mi_crm/.env
nano /var/www/mi_crm/.env
```

Fill in these values at minimum:

```ini
# Generate a new secret key (run the command below first)
SECRET_KEY=paste-generated-key-here

DEBUG=False
ALLOWED_HOSTS=micrm.microimageph.com

DB_ENGINE=mariadb
DB_NAME=mi_crm
DB_USER=mi_crm_user
DB_PASSWORD=YOUR_STRONG_PASSWORD

EMAIL_HOST_USER=crm_sales@microimageph.com
EMAIL_HOST_PASSWORD=your-smtp-password

REDMINE_API_KEY=your-redmine-api-key

SITE_URL=https://micrm.microimageph.com

CORS_ALLOW_ALL_ORIGINS=False
CORS_ALLOWED_ORIGINS=https://micrm.microimageph.com

# Real-time WebSocket channel layer (Warehouse Deliveries feed)
REDIS_URL=redis://127.0.0.1:6379/0
```

Generate the secret key:
```bash
source /var/www/mi_crm/venv/bin/activate
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Lock down the `.env` file permissions:
```bash
sudo chown root:www-data /var/www/mi_crm/.env
sudo chmod 640 /var/www/mi_crm/.env
```

---

### Step 7 — Run Django migrations and load seed data

```bash
cd /var/www/mi_crm
source venv/bin/activate

# Create all database tables
python manage.py migrate --noinput

# Load the seed data (users, teams, groups, lead sources)
python manage.py loaddata seed_backup_2026-07-22_174119.json

# Verify the import
python manage.py shell -c "
from users.models import User
from teams.models import Team, Group
from lead_generation.models import LeadSource
print(f'Users: {User.objects.count()}')
print(f'Teams: {Team.objects.count()}')
print(f'Groups: {Group.objects.count()}')
print(f'Lead Sources: {LeadSource.objects.count()}')
"

# Collect all static files into staticfiles/
python manage.py collectstatic --noinput
```

---

### Step 8 — Set file permissions

```bash
sudo chown -R www-data:www-data /var/www/mi_crm/media
sudo chown -R www-data:www-data /var/www/mi_crm/staticfiles
sudo chmod -R 755 /var/www/mi_crm
sudo chmod 640 /var/www/mi_crm/.env
```

---

### Step 9 — Configure nginx

```bash
# Copy the site config
sudo cp /var/www/mi_crm/etc/micrm_nginx /etc/nginx/sites-available/micrm_nginx

# Enable the site, disable the default placeholder
sudo ln -sf /etc/nginx/sites-available/micrm_nginx /etc/nginx/sites-enabled/micrm_nginx
sudo rm -f /etc/nginx/sites-enabled/default

# Test the configuration — must say "test is successful"
sudo nginx -t

# Apply
sudo systemctl reload nginx
```

---

### Step 10 — Set up SSL (HTTPS)

```bash
sudo certbot --nginx -d micrm.microimageph.com
```

Certbot will automatically update the nginx config with your certificate and set up auto-renewal. Test it:

```bash
sudo certbot renew --dry-run
```

---

### Step 11 — Enable the ASGI service (WebSocket feed)

The Warehouse Deliveries board streams live updates over `/ws/`. If
`/etc/systemd/system/mi_crm_daphne.service` does not exist yet, create it and
start Redis — full details in
[PRODUCTION_DEPLOY.md §8](PRODUCTION_DEPLOY.md#8-real-time-websockets-daphne--redis).

```bash
sudo systemctl enable --now redis-server
sudo systemctl enable --now mi_crm_daphne
sudo systemctl restart gunicorn mi_crm_daphne
```

---

### Step 12 — Configure the firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

---

### Step 13 — Create the Django admin superuser

```bash
cd /var/www/mi_crm
source venv/bin/activate
python manage.py createsuperuser
```

Follow the prompts to set username, email, and password for the admin account.

---

## 10. Post-Deployment Checklist

Run through this list after every fresh deployment to confirm everything is healthy.

```bash
cd /var/www/mi_crm
source venv/bin/activate

# 1. Django security check (fix any WARNINGS before going live)
python manage.py check --deploy

# 2. Confirm site responds
curl -I https://micrm.microimageph.com
# Expect: HTTP/2 200

# 3. Confirm HTTP redirects to HTTPS
curl -I http://micrm.microimageph.com
# Expect: 301 Moved Permanently → https://micrm.microimageph.com

# 4. Check nginx is running
sudo systemctl status nginx

# 5. Check the app services are running
sudo systemctl status gunicorn
sudo systemctl status mi_crm_daphne
sudo systemctl status redis-server

# 6. Check MariaDB is running
sudo systemctl status mariadb

# 7. Check error log is clean
sudo tail -20 /var/log/nginx/error.log
```

**Manual browser checks:**

- [ ] Login page loads at `https://micrm.microimageph.com/login/`
- [ ] Admin panel loads at `https://micrm.microimageph.com/admin/`
- [ ] Static files load (CSS and JS render correctly — no broken styles)
- [ ] File upload works (try uploading a file in File Sharing)
- [ ] Email sends (trigger a proposal email or test via Django shell)
- [ ] Warehouse Deliveries board shows a green **Live** badge (WebSocket connected)
- [ ] Brief **Reconnecting…** during load is acceptable if it quickly returns to **Live**

---

## 11. Updating the Production Server

When new code is ready on the development machine:

**Step 1 — Push updated code to the server**

```bash
# From your local machine (uses the existing deploy script)
./deploy_crm_office.sh     # stage
./deploy_crm_azure.sh      # production
```

**Step 2 — Restart the ASGI service**

```bash
cd /var/www/mi_crm
sudo systemctl restart mi_crm_daphne
```

The deploy scripts run in order: `pip install` → `migrate` → `collectstatic` →
`check` → restart `gunicorn`.

> **Always restart `mi_crm_daphne` as well.** It holds the old code in memory, so
> without a restart the WebSocket feed keeps the previous behaviour even though
> Gunicorn reloaded. See
> [PRODUCTION_DEPLOY.md §11](PRODUCTION_DEPLOY.md#11-subsequent-deploys-updates).

**If there is a new migration** the migrate step handles it automatically. If it
fails, check the output and resolve before restarting the services.

---

## 12. Admin Panel

The Django admin panel is available at:

```
https://micrm.microimageph.com/admin/
```

Log in with the superuser account created in Step 13 of the deployment. From here you can:

- Create, edit, and deactivate users
- Manage teams, groups, and memberships
- View and manage all model records
- Manage API tokens for the Android app
- Configure approval tiers for proposals
- View authentication tokens

---

## 13. Routine Maintenance

### Check nginx logs daily (first week after go-live)
```bash
sudo tail -f /var/log/nginx/error.log
```

### MariaDB backup (weekly recommended)
```bash
mysqldump -u mi_crm_user -p mi_crm > /home/your_user/mi_crm_db_$(date +%Y-%m-%d).sql
```

Restore from a SQL dump:
```bash
mysql -u mi_crm_user -p mi_crm < /home/your_user/mi_crm_db_2026-07-22.sql
```

### Re-export seed data backup (after adding new users or teams)
```bash
cd /var/www/mi_crm
source venv/bin/activate
python manage.py backup_seed_data --output /home/your_user/seed_$(date +%Y-%m-%d).json
```

### SSL certificate renewal (automatic via certbot)
Certbot installs a systemd timer that renews certificates automatically. To manually check:
```bash
sudo certbot renew --dry-run
sudo systemctl status certbot.timer
```

### Disk space — watch the media directory
User uploads accumulate in `/var/www/mi_crm/media/`. Check size:
```bash
du -sh /var/www/mi_crm/media/
```

---

## 14. Troubleshooting Reference

### Site shows the nginx default page instead of the CRM
```bash
sudo ln -sf /etc/nginx/sites-available/micrm_nginx /etc/nginx/sites-enabled/micrm_nginx
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### HTTP 502 Bad Gateway / 500 Internal Server Error
```bash
# 502 = nginx cannot reach Gunicorn
sudo systemctl status gunicorn
sudo journalctl -u gunicorn -n 50
ls -l /run/gunicorn.sock

# 500 = Django raised; check the app
sudo tail -50 /var/log/nginx/error.log
source /var/www/mi_crm/venv/bin/activate
cd /var/www/mi_crm
python manage.py check
```

### Static files (CSS/JS) not loading (styles broken)
```bash
source /var/www/mi_crm/venv/bin/activate
cd /var/www/mi_crm
python manage.py collectstatic --noinput --clear
sudo chown -R www-data:www-data /var/www/mi_crm/staticfiles
sudo systemctl reload nginx
```

### `ModuleNotFoundError: No module named 'MySQLdb'`
```bash
sudo apt-get install -y libmariadb-dev libmariadb-dev-compat
source /var/www/mi_crm/venv/bin/activate
pip install mysqlclient==2.2.6
sudo systemctl restart gunicorn
```

### `ModuleNotFoundError: No module named 'decouple'`
```bash
source /var/www/mi_crm/venv/bin/activate
pip install python-decouple==3.8
sudo systemctl restart gunicorn
```

### `ModuleNotFoundError: No module named 'channels'`
```bash
source /var/www/mi_crm/venv/bin/activate
cd /var/www/mi_crm
pip install channels==4.2.2 channels-redis==4.2.1 daphne==4.2.1
sudo systemctl restart gunicorn mi_crm_daphne
```

### Warehouse "Live" badge stays on "Reconnecting…"
```bash
sudo systemctl status mi_crm_daphne
redis-cli ping                      # expect PONG
grep -n "location /ws/" /etc/nginx/sites-available/micrm_nginx
```
See [PRODUCTION_DEPLOY.md §12](PRODUCTION_DEPLOY.md#12-troubleshooting) for the full checklist.

If the badge only flashes **Reconnecting…** briefly and then returns to **Live**,
the socket most likely reconnected successfully after a page load, restart, or
short network interruption.

### Database connection refused
```bash
sudo systemctl status mariadb
sudo systemctl start mariadb
sudo systemctl enable mariadb   # auto-start on reboot
```

### `Access denied for user 'mi_crm_user'@'localhost'`
```bash
sudo mysql -u root -p
```
```sql
GRANT ALL PRIVILEGES ON mi_crm.* TO 'mi_crm_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

### `.env` values not loading (settings still showing defaults)
```bash
# Confirm .env exists in project root
ls -la /var/www/mi_crm/.env

# Test python-decouple can read it
source /var/www/mi_crm/venv/bin/activate
cd /var/www/mi_crm
python -c "from decouple import config; print('DEBUG =', config('DEBUG'))"
```

### `loaddata` fails with integrity / foreign key errors
This usually means `contenttypes` got out of sync. Run:
```bash
source /var/www/mi_crm/venv/bin/activate
cd /var/www/mi_crm
python manage.py migrate --run-syncdb
python manage.py loaddata seed_backup_YYYY-MM-DD_HHMMSS.json
```

### nginx config test fails
```bash
sudo nginx -t
# Read the error carefully — usually a missing SSL certificate path or syntax error
# Edit the config to fix:
sudo nano /etc/nginx/sites-available/micrm_nginx
sudo systemctl reload nginx
```

### MFA locked out (user can't log in)
From the Django admin panel (`/admin/`), go to **MFA > Authenticators** and delete the user's TOTP authenticator record. They can then re-enroll.

---

## 15. Important Credentials & Contacts

> **Security note:** Do not store actual passwords in this document. Use a secure password manager (e.g., Bitwarden, KeePass) and share access with the Teamlead separately.

| Item | Where to find it |
|---|---|
| Django `SECRET_KEY` | `/var/www/mi_crm/.env` on the server |
| MariaDB `mi_crm_user` password | `/var/www/mi_crm/.env` → `DB_PASSWORD` |
| MariaDB root password | Password manager |
| SMTP password (`crm_sales@microimageph.com`) | `/var/www/mi_crm/.env` → `EMAIL_HOST_PASSWORD` |
| Redmine API key | `/var/www/mi_crm/.env` → `REDMINE_API_KEY` |
| Server SSH access | IT / sysadmin team |
| SSL certificate renewal | Automatic via certbot (check `sudo certbot renew --dry-run`) |
| Django admin superuser | Set during Step 13 of deployment |

**Email used by the system:** `crm_sales@microimageph.com`  
**Email server:** `email.microimageph.com:587` (TLS)  
**Redmine server:** `http://10.30.30.131` (internal network)  
**Redmine project:** ID `14` (Support), Tracker ID `7` (On-site Support)  
**Company website:** `https://www.microimageph.com`

---

*Document prepared by the development team — Micro Image International Corp. — July 2026*  
*For questions about the codebase, contact the original developer before making structural changes.*
