# MiCRM — Production Deployment Guide

**Target environment:** Ubuntu 22.04 LTS · nginx · Gunicorn (WSGI) · Daphne (ASGI) · Redis · MariaDB 10.6 · Python 3.10+

**Domain:** `https://micrm.microimageph.com`

---

## Table of Contents

1. [Overview of Changes Made](#1-overview-of-changes-made)
2. [Pre-Deployment: Back Up SQLite Data](#2-pre-deployment-back-up-sqlite-data)
3. [Server Prerequisites](#3-server-prerequisites)
4. [Deploy the Application](#4-deploy-the-application)
5. [Configure .env on the Server](#5-configure-env-on-the-server)
6. [Import Backup Data into MariaDB](#6-import-backup-data-into-mariadb)
7. [The HTTP Stack: Gunicorn + nginx](#7-the-http-stack-gunicorn--nginx)
8. [Real-Time WebSockets: Daphne + Redis](#8-real-time-websockets-daphne--redis)
9. [Set Up SSL with Let's Encrypt](#9-set-up-ssl-with-lets-encrypt)
10. [Post-Deployment Checklist](#10-post-deployment-checklist)
11. [Subsequent Deploys (Updates)](#11-subsequent-deploys-updates)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Overview of Changes Made

The following files were modified from the development version to prepare for production:

| File | Change |
|---|---|
| `dependencies/requirements.txt` | Added `mysqlclient==2.2.6` (MariaDB driver), `python-decouple==3.8` (env vars), and `channels` / `channels-redis` / `daphne` (real-time WebSockets) |
| `crm_project/settings.py` | Removed PostgreSQL, added MariaDB, moved all secrets to env vars via `python-decouple`, added production security headers, added `CHANNEL_LAYERS` (Redis or in-memory) |
| `crm_project/asgi.py` | `ProtocolTypeRouter` serving both `http` and `websocket` (via `AuthMiddlewareStack`) — used by Daphne |
| `etc/micrm_nginx` | nginx site config: HTTPS, security headers, static/media, ufw-friendly admin lockdown, and a `/ws/` reverse proxy to Daphne for WebSockets |
| `.env.example` | Template for all required environment variables |
| `.gitignore` | Ensures `.env` and `db.sqlite3` are never committed |
| `deploy2.sh` / `deploy_crm_office.sh` / `deploy_crm_azure.sh` | rsync + `migrate` + `collectstatic` + restart Gunicorn |

> **Note:** Apache (`apache_crm.conf`) is no longer used in staging or production — it has been removed from the repo. All web serving goes through nginx.

---

## 2. Pre-Deployment: Back Up SQLite Data

Run these commands **on your local development machine** before copying files to the server.

```bash
cd /Users/greg/Documents/mi_crm_v2
source venv/bin/activate   # or however you activate your local venv

# Export all app data to a JSON fixture (excludes framework-internal tables)
python manage.py dumpdata \
  --natural-foreign \
  --natural-primary \
  --exclude=contenttypes \
  --exclude=auth.permission \
  --indent=2 \
  -o db_backup.json

echo "Backup created: db_backup.json ($(wc -l < db_backup.json) lines)"
```

Keep `db_backup.json` safe — you will upload it to the server and import it into MariaDB in Step 6.

> **Note:** `db_backup.json` is listed in `.gitignore` and will not be committed. Transfer it manually via `scp` or `rsync`.

---

## 3. Server Prerequisites

SSH into your Ubuntu 22.04 server and run:

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y \
    python3 python3-pip python3-venv python3-dev \
    nginx \
    mariadb-server mariadb-client libmariadb-dev pkg-config \
    redis-server \
    git curl ufw certbot python3-certbot-nginx
```

Secure MariaDB:

```bash
sudo mysql_secure_installation
# Answer: set root password, remove anonymous users, disallow remote root login,
# remove test database, reload privilege tables — all Yes.
```

Create the database and user:

```bash
sudo mysql -u root -p
```

```sql
CREATE DATABASE mi_crm CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'mi_crm_user'@'localhost' IDENTIFIED BY 'YOUR_STRONG_PASSWORD';
GRANT ALL PRIVILEGES ON mi_crm.* TO 'mi_crm_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

---

## 4. Deploy the Application

**From your local machine**, use the existing deploy script (it rsyncs the working tree, runs migrations, collects static files, and restarts Gunicorn):

```bash
# Office / staging server
./deploy_crm_office.sh

# Production server
./deploy_crm_azure.sh
```

Both scripts **exclude `.env`, `venv`, `media`, `db.sqlite3`, and `.git`**, so the server keeps its own secrets and uploads. Use `--dry-run` first if you want to preview the file list.

If you prefer to rsync manually:

```bash
rsync -avz --progress \
  --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='venv' --exclude='db.sqlite3' \
  --exclude='staticfiles' --exclude='media' --exclude='.env' \
  /Users/greg/Documents/mi_crm_v2/ \
  your_user@your_server_ip:/var/www/mi_crm/
```

Also copy the backup file:

```bash
scp db_backup.json your_user@your_server_ip:/var/www/mi_crm/
```

**On the server**, set up the virtual environment and install dependencies:

```bash
cd /var/www/mi_crm

python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip wheel
pip install -r dependencies/requirements.txt
```

> `dependencies/requirements.txt` includes the real-time stack: `channels`, `channels-redis`, and `daphne`. If you maintain a separate prod pin file, make sure those three lines are present — otherwise `manage.py check` fails with `ModuleNotFoundError: No module named 'channels'`.

If you prefer to install just the WebSocket packages explicitly:

```bash
pip install channels==4.2.2 channels-redis==4.2.1 daphne==4.2.1
```

---

## 5. Configure .env on the Server

Create the `.env` file from the example template:

```bash
cp /var/www/mi_crm/.env.example /var/www/mi_crm/.env
nano /var/www/mi_crm/.env
```

Fill in every value. The minimum required settings for production:

```ini
# Generate with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
SECRET_KEY=your-generated-secret-key-here

DEBUG=False
ALLOWED_HOSTS=micrm.microimageph.com

DB_ENGINE=mariadb
DB_NAME=mi_crm
DB_USER=mi_crm_user
DB_PASSWORD=YOUR_STRONG_PASSWORD
DB_HOST=127.0.0.1
DB_PORT=3306

EMAIL_HOST_USER=crm_sales@microimageph.com
EMAIL_HOST_PASSWORD=your-email-password

REDMINE_API_KEY=your-redmine-api-key

# IMPORTANT: Set this to your server's actual domain or IP — used to build
# absolute URLs in campaign emails (unsubscribe and interested buttons).
# Without this, email links will be broken and point to localhost.
SITE_URL=https://micrm.microimageph.com

CORS_ALLOW_ALL_ORIGINS=False
CORS_ALLOWED_ORIGINS=https://micrm.microimageph.com

# Real-time WebSocket channel layer (Warehouse Deliveries feed).
# Leave blank ONLY for local single-process dev (in-memory fallback).
REDIS_URL=redis://127.0.0.1:6379/0
```

Lock down permissions on the `.env` file:

```bash
sudo chown root:www-data /var/www/mi_crm/.env
sudo chmod 640 /var/www/mi_crm/.env
```

---

## 6. Import Backup Data into MariaDB

This is the core data migration step. Run in order:

```bash
cd /var/www/mi_crm
source venv/bin/activate

# Step 1: Create all tables from Django migrations
python manage.py migrate --noinput

# Step 2: Fix column lengths (SQLite doesn't enforce max_length, MariaDB does)
# Some existing data exceeds the original field limits. Widen them before loading:
python manage.py dbshell
```

Run these SQL commands inside the MariaDB shell:

```sql
ALTER TABLE customers_customer MODIFY company_name VARCHAR(255);
ALTER TABLE customers_customer MODIFY phone_number VARCHAR(100);
ALTER TABLE customers_customercreaterequest MODIFY company_name VARCHAR(255);
ALTER TABLE customers_customercreaterequest MODIFY phone_number VARCHAR(100);
EXIT;
```

> **Why?** SQLite doesn't enforce `CharField(max_length=...)` limits — it happily stores any length string. MariaDB enforces them strictly. If `loaddata` fails with `"Data too long for column X"`, widen that column using `ALTER TABLE ... MODIFY column_name VARCHAR(new_length);` and retry.

```bash
# Step 3: Load the SQLite data dump into MariaDB
python manage.py loaddata db_backup.json

# Step 4: Verify the import
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
print(f'Users imported: {User.objects.count()}')
from customers.models import Customer
print(f'Customers imported: {Customer.objects.count()}')
from sales_proposals.models import Proposal
print(f'Proposals imported: {Proposal.objects.count()}')
from sales_funnel.models import SalesFunnel
print(f'Funnel entries imported: {SalesFunnel.objects.count()}')
"
```

> **If `loaddata` fails with "Data too long" errors**, identify the field from the error message and widen it:
> ```bash
> python manage.py dbshell
> ```
> ```sql
> -- Example: if 'contact_person_name' is too long
> ALTER TABLE customers_customer MODIFY contact_person_name VARCHAR(255);
> EXIT;
> ```
> Then retry `python manage.py loaddata db_backup.json`.

> **If `loaddata` fails with integrity errors** (content types or permissions), the backup should already exclude those. If not, re-export from SQLite:
> ```bash
> python manage.py dumpdata \
>   --natural-foreign --natural-primary \
>   --exclude=contenttypes --exclude=auth.permission \
>   --indent=2 -o db_backup.json
> ```

Collect static files:

```bash
python manage.py collectstatic --noinput
```

Seed activity types (if not already in the backup):

```bash
python manage.py populate_activity_types
```

---

## 7. The HTTP Stack: Gunicorn + nginx

Two processes serve the site:

| Layer | Role | Address |
|---|---|---|
| **Gunicorn** (systemd service `gunicorn`) | Runs Django WSGI — all normal HTTP requests | Unix socket `/run/gunicorn.sock` |
| **nginx** | TLS termination, static/media, security headers, reverse proxy | ports 80 / 443 |

> This stack is **already running on your staging and production servers**. The
> sections below document it for reference and rebuilds.

### 7.1 Gunicorn systemd service

`/etc/systemd/system/gunicorn.service`:

```ini
[Unit]
Description=MiCRM Gunicorn (WSGI) daemon
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/mi_crm
Environment="PATH=/var/www/mi_crm/venv/bin"
ExecStart=/var/www/mi_crm/venv/bin/gunicorn \
    --workers 4 \
    --bind unix:/run/gunicorn.sock \
    crm_project.wsgi:application
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now gunicorn
sudo systemctl status gunicorn --no-pager
```

> If Gunicorn cannot create the socket directly in `/run`, add
> `RuntimeDirectory=mi_crm` to `[Service]` and change the bind to
> `unix:/run/mi_crm/gunicorn.sock`, then update `proxy_pass` in the nginx config
> to the same path. Keep the two in sync.

### 7.2 nginx site configuration

The site config lives in the repo at [etc/micrm_nginx](../etc/micrm_nginx) and is
deployed to `/etc/nginx/sites-available/micrm_nginx`:

```bash
sudo cp /var/www/mi_crm/etc/micrm_nginx /etc/nginx/sites-available/micrm_nginx
sudo ln -sf /etc/nginx/sites-available/micrm_nginx /etc/nginx/sites-enabled/micrm_nginx
sudo nginx -t                       # must say "syntax is ok" / "test is successful"
sudo systemctl reload nginx
```

The config handles:

- **HTTP → HTTPS redirect** (301) for `micrm.microimageph.com`.
- **TLS** (certificates managed by Certbot, see Step 9).
- **Security headers** — HSTS, `X-Frame-Options`, `X-Content-Type-Options`, `X-XSS-Protection`, `Referrer-Policy`, CSP, and `Permission-Policy`.
- **`client_max_body_size 150M`** — required so large uploads (e.g. the company-wide Android APK) are not rejected with HTTP 413 before reaching Django.
- **`/static/`** → `/var/www/mi_crm/staticfiles/` and **`/media/`** → `/var/www/mi_crm/media/`, served directly by nginx with long cache headers.
- **`/admin`** → restricted to private networks (`allow 10.0.0.0/8`, `192.168.0.0/16`, `deny all`) and proxied to Gunicorn.
- **`/ws/`** → reverse-proxied to Daphne (added for the Warehouse Deliveries feed — see Step 8).
- **`/`** → proxied to the Gunicorn unix socket.

> The `default_server` block at the top uses `ssl_reject_handshake on;` so requests
> to an unknown hostname are dropped before an SSL certificate is negotiated.

---

## 8. Real-Time WebSockets: Daphne + Redis

The **Warehouse Deliveries** board pushes live updates over a WebSocket
(`/ws/warehouse/deliveries/`) using Django Channels. There are **three** moving
parts, and all three must be in place on stage/production:

1. **`channels` / `channels-redis` / `daphne` installed in the venv** (Step 4 —
   otherwise `python manage.py check` fails with
   `ModuleNotFoundError: No module named 'channels'`).
2. **Redis running** and `REDIS_URL` set in `.env` (Step 5).
3. **Daphne running as an ASGI service**, with nginx reverse-proxying `/ws/` to
   it.

> **Why a second server?** Gunicorn is a **WSGI** server. WSGI cannot upgrade an
> HTTP connection to a WebSocket, so it can never serve `/ws/`. Gunicorn keeps
> handling all normal HTTP; Daphne handles only the WebSocket connections.

### 8.1 Install the Python packages

Already covered in Step 4 if you installed `dependencies/requirements.txt`. To do
it standalone:

```bash
cd /var/www/mi_crm
source venv/bin/activate
pip install channels==4.2.2 channels-redis==4.2.1 daphne==4.2.1
```

Verify:

```bash
python -c "import channels, channels_redis, daphne; print('OK')"
```

### 8.2 Install and start Redis

```bash
sudo apt-get install -y redis-server
sudo systemctl enable --now redis-server
redis-cli ping        # expect: PONG
```

Security notes (keep it local-only):

- Redis listens on `127.0.0.1:6379` by default — **do not** expose port 6379 to
  the network or change `bind` to `0.0.0.0`.
- Optionally set a password in `/etc/redis/redis.conf`:
  ```ini
  requirepass YOUR_REDIS_PASSWORD
  ```
  then use `REDIS_URL=redis://:YOUR_REDIS_PASSWORD@127.0.0.1:6379/0` in `.env`
  and restart both Redis and Daphne.

> **Why Redis on the server?** Gunicorn runs **4 workers** (`--workers 4` in
> Step 7.1). The in-memory channel layer lives inside a single process, so a
> delivery update saved by worker A would never reach a board served by worker B.
> Redis shares the channel layer across all workers (and across the Daphne
> process), making live updates consistent for everyone.

### 8.3 Run Daphne as a systemd service

If `/etc/systemd/system/mi_crm_daphne.service` does not exist yet, create it:

```ini
[Unit]
Description=MiCRM Daphne ASGI (WebSocket) service
After=network.target redis-server.service
Wants=redis-server.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/mi_crm
Environment="PATH=/var/www/mi_crm/venv/bin"
ExecStart=/var/www/mi_crm/venv/bin/daphne -b 127.0.0.1 -p 8001 crm_project.asgi:application
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mi_crm_daphne
sudo systemctl status mi_crm_daphne --no-pager
```

> Bind to `127.0.0.1` (not `0.0.0.0`) so Daphne is reachable only through nginx.
> Port `8001` is internal and independent of the Gunicorn socket.
>
> If the service already exists on staging/production, you do not need to
> recreate it. Just verify it is active:
>
> ```bash
> sudo systemctl status mi_crm_daphne --no-pager
> ```

### 8.4 Proxy `/ws/` from nginx to Daphne

This is the **only WebSocket-specific change** made to the working nginx config.
Everything else in [etc/micrm_nginx](../etc/micrm_nginx) is unchanged.

If the config does not already have it, add this `location` block inside the
**`listen 443 ssl http2`** `server` block, **before** the existing `location / {`:

```nginx
# WebSocket — Warehouse Deliveries real-time feed -> Daphne (ASGI)
#
# Gunicorn is a WSGI server and cannot upgrade a connection to WebSocket,
# so /ws/ is proxied to the Daphne service listening on 127.0.0.1:8001
# instead of the gunicorn socket. This prefix location is longer than
# "location /", so nginx routes /ws/ here and everything else to gunicorn.
location /ws/ {
    proxy_pass http://127.0.0.1:8001;

    # Required for the HTTP -> WebSocket upgrade handshake
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port $server_port;

    # WebSockets are long-lived: do not time them out like normal requests
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    proxy_buffering off;
}
```

Why each piece matters:

| Directive | Purpose |
|---|---|
| `proxy_http_version 1.1` | WebSocket upgrades require HTTP/1.1 (nginx defaults to 1.0 upstream) |
| `Upgrade` / `Connection "upgrade"` | Performs the actual protocol upgrade handshake |
| `proxy_read_timeout 3600s` | The default 60s would kill an idle-but-open WebSocket |
| `proxy_buffering off` | Ensures frames are pushed immediately, not buffered |

Then deploy and reload:

```bash
sudo cp /var/www/mi_crm/etc/micrm_nginx /etc/nginx/sites-available/micrm_nginx
sudo nginx -t && sudo systemctl reload nginx
```

> **No CSP change is needed.** The existing
> `Content-Security-Policy` header has no explicit `connect-src`, so it falls back
> to `default-src 'self'` — which already permits a same-origin `wss://`
> connection.

### 8.5 Verify

```bash
# Daphne is up and serving Django over ASGI
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8001/warehouse/

# WebSocket routed through nginx -> Daphne (a 403 is a PASS: it reached
# Channels and was rejected for being unauthenticated; 404/502 means the
# proxy or Daphne is misconfigured)
curl -s -o /dev/null -w '%{http_code}\n' \
  -H 'Upgrade: websocket' -H 'Connection: Upgrade' \
  https://micrm.microimageph.com/ws/warehouse/deliveries/
```

Then open the Warehouse Deliveries board while logged in — the header badge
should read **Live** (green).

Notes on the badge:

- A brief **Reconnecting…** state during page load, right after a deploy/restart,
  or after a short network hiccup is normal if it quickly returns to **Live**.
- Treat it as a problem only if it stays on **Reconnecting…** or live updates do
  not arrive.

If it stays **Reconnecting…**, check `sudo journalctl -u mi_crm_daphne -n 50`
and `/var/log/nginx/error.log`.

### 8.6 Stage server vs production server

The steps are identical; only these values differ.

| Item | Stage (office) | Production (azure) |
|---|---|---|
| Deploy script | `./deploy_crm_office.sh` | `./deploy_crm_azure.sh` |
| SSH host alias | `crm_office` | `crm_azure` |
| Domain / `ALLOWED_HOSTS` / `SITE_URL` / `CORS_ALLOWED_ORIGINS` | stage hostname or office IP | `micrm.microimageph.com` |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` (or `/1` if Redis is shared) | `redis://127.0.0.1:6379/0` |
| Daphne service name | `mi_crm_daphne` | `mi_crm_daphne` |
| Daphne bind port | `8001` | `8001` |

> Run the same sections **3 → 4 → 5 → 7 → 8** on the stage server so it behaves
> like production. Use a **separate Redis logical DB** if stage and production
> ever share one Redis instance (e.g. stage `/1`, production `/0`).

---

## 9. Set Up SSL with Let's Encrypt

```bash
sudo certbot --nginx -d micrm.microimageph.com
```

Certbot will automatically update the nginx config with your SSL certificate paths and set up auto-renewal. Test renewal:

```bash
sudo certbot renew --dry-run
```

Verify auto-renewal is scheduled:

```bash
sudo systemctl status certbot.timer
```

> **If you ran Certbot before Step 8.4:** Certbot rewrites the server block when
> it installs the certificate. Re-check that the `location /ws/` block is still
> inside the `listen 443 ssl` server block and still **above** `location / {` —
> a misplaced block silently breaks the WebSocket feed while the HTTP site keeps
> working.
> ```bash
> grep -n "location /ws/\|location / {" /etc/nginx/sites-available/micrm_nginx
> ```

---

## 10. Post-Deployment Checklist

Run all of these on the server before going live:

```bash
cd /var/www/mi_crm
source venv/bin/activate

# Django deployment check (reports any security issues)
python manage.py check --deploy

# Set correct ownership for writable directories
sudo chown -R www-data:www-data /var/www/mi_crm/media
sudo chown -R www-data:www-data /var/www/mi_crm/staticfiles

# Install and enable the nginx site config
sudo cp /var/www/mi_crm/etc/micrm_nginx /etc/nginx/sites-available/micrm_nginx
sudo ln -sf /etc/nginx/sites-available/micrm_nginx /etc/nginx/sites-enabled/micrm_nginx
sudo rm -f /etc/nginx/sites-enabled/default   # disable default site
sudo nginx -t                                 # must say "test is successful"
sudo systemctl reload nginx

# Start Gunicorn, Daphne (real-time WebSockets) and Redis
sudo systemctl enable --now gunicorn
sudo systemctl enable --now redis-server
sudo systemctl enable --now mi_crm_daphne
sudo systemctl restart gunicorn mi_crm_daphne

# Configure firewall
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status

# Create the first admin user
python manage.py createsuperuser
```

Verify all three surfaces are live:

```bash
# Normal HTTP (nginx -> Gunicorn)
curl -I https://micrm.microimageph.com
# Expect: HTTP/2 200 (or 301 from HTTP)

# Gunicorn is answering on its socket
sudo systemctl is-active gunicorn

# Daphne directly
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8001/warehouse/
# Expect: 302 (redirect to login — Daphne is serving Django over ASGI)
```

---

## 11. Subsequent Deploys (Updates)

After the initial setup, use the existing deploy script — it syncs the code,
installs new packages, migrates, collects static, and restarts Gunicorn:

```bash
# From your local machine
./deploy_crm_office.sh     # stage
./deploy_crm_azure.sh      # production
```

Then **restart Daphne** so the WebSocket side picks up the new code:

```bash
ssh -i ~/.ssh/id_rsa crm_office    # or ~/.susi/CRM_key.pem crm_azure
cd /var/www/mi_crm
sudo systemctl restart mi_crm_daphne
```

Or do the whole update manually on the server:

```bash
cd /var/www/mi_crm
source venv/bin/activate
pip install -r dependencies/requirements.txt
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py check
deactivate
sudo systemctl restart gunicorn mi_crm_daphne
sudo systemctl reload nginx
```

> **Always restart `mi_crm_daphne` after an update.** Daphne holds the old code
> in memory; without a restart, WebSocket clients keep the previous behaviour
> even though Gunicorn and nginx reloaded the HTTP side. Restarting the web tier
> alone is not enough.

---

## 12. Troubleshooting

### Site returns 502 Bad Gateway

nginx cannot reach Gunicorn.

```bash
sudo systemctl status gunicorn --no-pager
sudo journalctl -u gunicorn -n 50
ls -l /run/gunicorn.sock          # socket must exist and be writable by www-data
sudo tail -50 /var/log/nginx/error.log
```

Then confirm Django itself loads:

```bash
source /var/www/mi_crm/venv/bin/activate
cd /var/www/mi_crm
python manage.py check
```

### nginx config test fails

```bash
sudo nginx -t                     # shows the exact file and line
sudo systemctl reload nginx
```

### `No module named 'MySQLdb'`

```bash
source /var/www/mi_crm/venv/bin/activate
pip install mysqlclient
```

If `mysqlclient` fails to compile:

```bash
sudo apt-get install -y libmariadb-dev libmariadb-dev-compat
pip install mysqlclient
```

### `Access denied for user 'mi_crm_user'@'localhost'`

```bash
sudo mysql -u root -p
# Then re-run the GRANT statement from Step 3
GRANT ALL PRIVILEGES ON mi_crm.* TO 'mi_crm_user'@'localhost';
FLUSH PRIVILEGES;
```

### Static files returning 404

```bash
python manage.py collectstatic --noinput --clear
sudo chown -R www-data:www-data /var/www/mi_crm/staticfiles
sudo systemctl reload nginx
```

Confirm the `location /static/` alias in the nginx config points at
`/var/www/mi_crm/staticfiles/`.

### Uploads rejected with HTTP 413

nginx's `client_max_body_size` is too small. The site config sets `150M`; confirm
it is present and reload:

```bash
grep -n client_max_body_size /etc/nginx/sites-available/micrm_nginx
sudo nginx -t && sudo systemctl reload nginx
```

### `.env` variables not being read

Verify python-decouple is installed in the venv and the `.env` file is in `/var/www/mi_crm/` (the `BASE_DIR`):

```bash
source /var/www/mi_crm/venv/bin/activate
python -c "from decouple import config; print(config('DEBUG'))"
```

### `django.db.utils.OperationalError: (2002, "Can't connect to server")`

```bash
sudo systemctl status mariadb
sudo systemctl start mariadb
sudo systemctl enable mariadb
```

### `ModuleNotFoundError: No module named 'channels'`

The venv is missing the real-time stack. This is exactly what breaks
`manage.py check` right after an `rsync` (code copied, packages not installed).

```bash
cd /var/www/mi_crm
source venv/bin/activate
pip install -r dependencies/requirements.txt
# or just the three packages:
pip install channels==4.2.2 channels-redis==4.2.1 daphne==4.2.1
python manage.py check
```

### Warehouse board shows "Reconnecting…" for a long time (no live updates)

Work through the three parts of Step 8:

```bash
# 1. Is the ASGI service running?
sudo systemctl status mi_crm_daphne --no-pager
sudo journalctl -u mi_crm_daphne -n 50

# 2. Is Redis up?
redis-cli ping        # expect PONG
sudo systemctl status redis-server --no-pager

# 3. Did nginx proxy /ws/ ? (403 = reached Channels; 404/502 = not proxied)
curl -s -o /dev/null -w '%{http_code}\n' \
  -H 'Upgrade: websocket' -H 'Connection: Upgrade' \
  https://micrm.microimageph.com/ws/warehouse/deliveries/
```

Common causes:

- The `location /ws/` block is missing, or sits **after** `location / {` → move it above.
- `proxy_set_header Connection "upgrade"` missing → the handshake is rejected.
- `REDIS_URL` blank in `.env` (falls back to per-process in-memory layer) → set it and `sudo systemctl restart mi_crm_daphne`.
- Daphne not restarted after a code change → `sudo systemctl restart mi_crm_daphne`.
- A proxy in front of nginx (corporate/LAN proxy) blocking `wss://` → test from a different network.
- Browser console shows a CSP violation on `connect-src` → add `connect-src 'self' wss://micrm.microimageph.com` to the CSP header.

If the badge briefly flips to **Reconnecting…** and then returns to **Live**, that
usually means the browser re-established the socket successfully. Common benign
causes are a page refresh, nginx reload, Daphne restart, or a short network
blip. That behavior is acceptable as long as the board resumes receiving live
updates.

### Daphne fails to start / port already in use

```bash
sudo journalctl -u mi_crm_daphne -n 50
sudo ss -ltnp | grep 8001     # see what is holding the port
# then either free the port or pick another and update the nginx proxy_pass + unit file
```

---

*Generated for MiCRM — Micro Image International Corp.*
