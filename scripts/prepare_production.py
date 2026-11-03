import os
import sys
import subprocess

def run_command(command):
    print(f"Running: {command}")
    try:
        subprocess.check_call(command, shell=True)
        print("Success.")
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        sys.exit(1)

def main():
    print("="*50)
    print("MiCRM Production Preparation Script")
    print("="*50)

    # 1. Dump current data
    print("\nStep 1: Dumping data from SQLite3...")
    if os.path.exists('db.sqlite3'):
        # Exclude auth.permission and contenttypes to prevent conflicts during import
        # because these tables are automatically populated by Django during migration
        cmd = "python3 manage.py dumpdata --exclude auth.permission --exclude contenttypes --indent 2 > data_dump.json"
        run_command(cmd)
        print("Data dumped to 'data_dump.json'.")
    else:
        print("Warning: db.sqlite3 not found. Skipping data dump.")

    # 2. Create MySQL Configuration
    print("\nStep 2: Creating MySQL Configuration...")
    mysql_settings = """
# Local Settings for MySQL Production
from .settings import *

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'mi_crm_db',
        'USER': 'crm_user',
        'PASSWORD': 'your_secure_password',
        'HOST': 'localhost',
        'PORT': '3306',
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}
"""
    with open('crm_project/local_settings_mysql.py', 'w') as f:
        f.write(mysql_settings)
    print("Created 'crm_project/local_settings_mysql.py'.")

    # 3. Create Setup Script for the Server
    print("\nStep 3: Creating Server Setup Script (setup_mysql.sh)...")
    setup_script = """#!/bin/bash

# Exit on error
set -e

echo "Starting MySQL Setup & Data Import..."

# Check if local_settings_mysql.py exists
if [ ! -f "crm_project/local_settings_mysql.py" ]; then
    echo "Error: crm_project/local_settings_mysql.py not found!"
    exit 1
fi

# 1. Install Dependencies
echo "Installing Python dependencies..."
pip install -r dependencies/requirements-prod.txt

# 2. Update Settings to use MySQL
# We temporarily swap the settings file or rely on PYTHONPATH, 
# but here we'll append the import to the main settings if not present
if ! grep -q "try: from .local_settings_mysql import *; except ImportError: pass" crm_project/settings.py; then
    echo "Adding local_settings_mysql import to settings.py..."
    echo "" >> crm_project/settings.py
    echo "# Import MySQL settings if available" >> crm_project/settings.py
    echo "try: from .local_settings_mysql import *; except ImportError: pass" >> crm_project/settings.py
fi

# 3. Apply Migrations to MySQL
echo "Applying migrations to MySQL..."
python3 manage.py migrate

# 4. Load Data
if [ -f "data_dump.json" ]; then
    echo "Loading data from data_dump.json..."
    python3 manage.py loaddata data_dump.json
else
    echo "Warning: data_dump.json not found. Skipping data import."
fi

# 5. Collect Static Files
echo "Collecting static files..."
python3 manage.py collectstatic --noinput

echo "=========================================="
echo "Setup Complete!"
echo "Make sure to update 'crm_project/local_settings_mysql.py' with your actual database credentials."
echo "=========================================="
"""
    with open('setup_mysql.sh', 'w') as f:
        f.write(setup_script)
    
    # Make it executable
    os.chmod('setup_mysql.sh', 0o755)
    print("Created 'setup_mysql.sh'.")

    print("\n" + "="*50)
    print("PREPARATION COMPLETE")
    print("="*50)
    print("Files created:")
    print("1. data_dump.json (Database backup)")
    print("2. crm_project/local_settings_mysql.py (MySQL config template)")
    print("3. setup_mysql.sh (Script to run on the production server)")
    print("4. etc/micrm_nginx (nginx site configuration)")
    print("\nNext Steps for Production:")
    print("1. Copy this entire project to your production server.")
    print("2. Create the MySQL database and user:")
    print("   CREATE DATABASE mi_crm_db CHARACTER SET utf8mb4;")
    print("   CREATE USER 'crm_user'@'localhost' IDENTIFIED BY 'your_secure_password';")
    print("   GRANT ALL PRIVILEGES ON mi_crm_db.* TO 'crm_user'@'localhost';")
    print("   FLUSH PRIVILEGES;")
    print("3. Update 'crm_project/local_settings_mysql.py' with the password.")
    print("4. Run './setup_mysql.sh'")

if __name__ == "__main__":
    main()
