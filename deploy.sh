#!/bin/bash
#
# Deploy the CRM to production (crm_azure) via rsync, then run migrations,
# collect static files, and restart gunicorn.
#
# Safe-by-design:
#   * .env is EXCLUDED — production keeps its own secrets (SMTP password, SECRET_KEY,
#     MySQL creds). The synced settings.py reads them from prod's .env.
#   * db.sqlite3 / venv / media / .git / __pycache__ are excluded so prod data,
#     virtualenv, and uploads are never clobbered.
#
# Usage:
#   ./deploy.sh            # normal deploy (prompts before the destructive-ish steps)
#   ./deploy.sh --dry-run  # show what rsync WOULD copy, make no changes
#
set -euo pipefail

# ------------------------------------------------------------------ config ---
REMOTE_SVR="crm_azure"
REMOTE_DIR="/var/www/mi_crm"
#LOCAL_DIR="/private/var/www/mi_crm/"
LOCAL_DIR="/Users/greg/Documents/mi_crm_v2/"
SSH_KEY="$HOME/.susi/CRM_key.pem"
SSH="ssh -i $SSH_KEY"
GUNICORN_SERVICE="gunicorn"

DRY_RUN=""
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN="--dry-run"
    echo ">>> DRY RUN — no changes will be made."
fi

# ------------------------------------------------- pre-flight safety checks ---
echo ">>> Deploying branch: $(git rev-parse --abbrev-ref HEAD)  commit: $(git rev-parse --short HEAD)"

# 1) Warn on uncommitted changes (rsync copies the working tree as-is).
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    echo "!!! WARNING: you have uncommitted changes; rsync copies the working tree as-is."
fi

# 2) CRITICAL: prod must have EMAIL_HOST_PASSWORD in its .env, otherwise email
#    silently falls back to the file-based backend after settings.py is synced.
echo ">>> Checking prod .env for EMAIL_HOST_PASSWORD ..."
if $SSH "$REMOTE_SVR" "grep -q '^EMAIL_HOST_PASSWORD=' $REMOTE_DIR/.env" 2>/dev/null; then
    echo "    OK — prod .env has EMAIL_HOST_PASSWORD."
else
    echo "!!! ERROR: prod .env is missing EMAIL_HOST_PASSWORD (or .env not found)."
    echo "    Add it on the server BEFORE deploying, or outgoing email will stop:"
    echo "      ssh -i $SSH_KEY $REMOTE_SVR 'nano $REMOTE_DIR/.env'"
    echo "    (also confirm SECRET_KEY and the DB settings are present)"
    [[ -z "$DRY_RUN" ]] && exit 1
fi

# ------------------------------------------------------------------ confirm ---
if [[ -z "$DRY_RUN" ]]; then
    read -r -p ">>> Proceed with deploy to $REMOTE_SVR? [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }
fi

# --------------------------------------------------------------------- sync ---
echo ">>> Syncing code to $REMOTE_SVR:$REMOTE_DIR ..."
rsync -avz $DRY_RUN -e "$SSH" \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude 'db.sqlite3' \
    --exclude 'venv' \
    --exclude 'media' \
    --exclude 'MiCRM_Android' \
    --exclude 'micrm_android_mockup' \
    --exclude '.env' \
    --exclude 'recycle' \
    --exclude 'backup' \
    --exclude 'docs' \
    --exclude 'sent_emails' \
    "$LOCAL_DIR" "$REMOTE_SVR:$REMOTE_DIR/"

if [[ -n "$DRY_RUN" ]]; then
    echo ">>> DRY RUN complete. No remote commands were run."
    exit 0
fi

# ------------------------------------------- migrate / static / restart app ---
echo ">>> Running post-deploy steps on $REMOTE_SVR ..."
$SSH "$REMOTE_SVR" "bash -s" <<REMOTE
set -euo pipefail
cd "$REMOTE_DIR"
source venv/bin/activate

echo '--- migrate (all apps; applies only what is pending) ---'
python manage.py migrate --noinput

echo '--- collectstatic ---'
python manage.py collectstatic --noinput

echo '--- django system check ---'
python manage.py check

echo '--- restart gunicorn ---'
sudo systemctl restart $GUNICORN_SERVICE

echo '--- gunicorn status ---'
sudo systemctl is-active $GUNICORN_SERVICE
REMOTE

echo ">>> Deploy complete."
echo ">>> Smoke-test: load the site, open a proposal, and send a test email (e.g. password reset)."
