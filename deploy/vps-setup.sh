#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 VPS for Teacher Assist (run as root ON THE VPS):
#   bash vps-setup.sh ctetmonktest.fun you@example.com
# It asks for the database password and the app admin's password (never stored in git, only in /srv/teacher-assist/.env).
# Installs MariaDB, Python, nginx + a free HTTPS certificate, a firewall, and the systemd service.
# Afterwards send the code from the Mac with deploy/push-to-vps.sh.
set -euo pipefail

DOMAIN="${1:?usage: vps-setup.sh <domain> <email-for-https-notices>}"
EMAIL="${2:?usage: vps-setup.sh <domain> <email-for-https-notices>}"
APP_DIR=/srv/teacher-assist
APP_USER=teacher
DB_NAME=hpc_automation
DB_USER=hpc_app

read -rp  "App admin login [bilal]: " ADMIN_LOGIN; ADMIN_LOGIN="${ADMIN_LOGIN:-bilal}"
read -rsp "App admin password: " ADMIN_PASS; echo
read -rsp "Database password for ${DB_USER} (new): " DB_PASS; echo
[ -n "$ADMIN_PASS" ] && [ -n "$DB_PASS" ] || { echo "Both passwords are needed."; exit 1; }

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -yq
apt-get install -yq python3 python3-venv python3-dev build-essential mariadb-server nginx certbot \
  python3-certbot-nginx rsync ufw unattended-upgrades

# --- firewall: SSH and the website only
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

# --- the app's own user and folders
id "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash "$APP_USER"
mkdir -p "$APP_DIR" "$APP_DIR/data" /srv/teacher-assist-backups /srv/teacher-assist-keys
chown -R "$APP_USER:$APP_USER" "$APP_DIR" /srv/teacher-assist-backups /srv/teacher-assist-keys
chmod 700 "$APP_DIR/data" /srv/teacher-assist-backups /srv/teacher-assist-keys

# --- database (only reachable from this machine)
systemctl enable --now mariadb
DB_PASS_SQL="${DB_PASS//\'/\'\'}"
mysql <<SQL
CREATE DATABASE IF NOT EXISTS ${DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS_SQL}';
ALTER USER '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS_SQL}';
GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL

# --- .env (secrets live only here)
DB_PASS_URL=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1],safe=""))' "$DB_PASS")
JWT=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')
umask 077
cat > "$APP_DIR/.env" <<ENV
HPC_DATABASE_URL=mysql+pymysql://${DB_USER}:${DB_PASS_URL}@127.0.0.1:3306/${DB_NAME}?charset=utf8mb4
HPC_JWT_SECRET=${JWT}
HPC_DATA_DIR=${APP_DIR}/data
HPC_BACKUP_DIR=/srv/teacher-assist-backups
HPC_BACKUP_KEY_FILE=/srv/teacher-assist-keys/backup.key
HPC_COOKIE_SECURE=true
HPC_APP_ADMIN_LOGIN=${ADMIN_LOGIN}
HPC_APP_ADMIN_PASSWORD=${ADMIN_PASS}
ENV
chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"
umask 022

# --- the service (uvicorn on 127.0.0.1:8000, behind nginx)
cat > /etc/systemd/system/teacher-assist.service <<UNIT
[Unit]
Description=Teacher Assist
After=network.target mariadb.service

[Service]
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable teacher-assist

# --- the code-push user may restart only this service
cat > /etc/sudoers.d/teacher-assist <<SUDO
${APP_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl restart teacher-assist, /usr/bin/systemctl status teacher-assist
SUDO
chmod 440 /etc/sudoers.d/teacher-assist
if [ -f /root/.ssh/authorized_keys ]; then
  mkdir -p "/home/${APP_USER}/.ssh"
  cp /root/.ssh/authorized_keys "/home/${APP_USER}/.ssh/authorized_keys"
  chown -R "$APP_USER:$APP_USER" "/home/${APP_USER}/.ssh"
  chmod 700 "/home/${APP_USER}/.ssh"; chmod 600 "/home/${APP_USER}/.ssh/authorized_keys"
fi

# --- nginx in front, then HTTPS
cat > /etc/nginx/sites-available/teacher-assist <<NGINX
server {
    listen 80;
    server_name ${DOMAIN} www.${DOMAIN};
    client_max_body_size 25m;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
NGINX
ln -sf /etc/nginx/sites-available/teacher-assist /etc/nginx/sites-enabled/teacher-assist
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
certbot --nginx --non-interactive --agree-tos -m "$EMAIL" -d "$DOMAIN" -d "www.$DOMAIN" --redirect \
  || echo "HTTPS not issued yet: point ${DOMAIN} and www.${DOMAIN} (A records) at this server, then run: certbot --nginx -d ${DOMAIN} -d www.${DOMAIN} --redirect"

echo
echo "VPS ready. Now, on the Mac:  bash deploy/push-to-vps.sh <VPS-IP>"
