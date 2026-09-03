#!/usr/bin/env bash
# Installe et démarre l'application sur un VPS Ubuntu/Debian.
# Usage (en root sur le serveur) :
#   bash deploy/deploy.sh
#
# Avant de lancer, téléverse ta base existante si tu veux la conserver :
#   scp data/listings.db data/listings_fr.db root@IP_DU_VPS:/opt/invest_tracker/data/
set -euo pipefail

APP_DIR="/opt/invest_tracker"
REPO_URL="${REPO_URL:-https://github.com/VOTRE_COMPTE/invest_tracker.git}"

echo "== 1/7 Packages systeme =="
apt-get update
apt-get install -y python3 python3-venv python3-pip nginx git sqlite3

echo "== 2/7 Code source =="
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull
else
  git clone "$REPO_URL" "$APP_DIR"
fi

echo "== 3/7 Environnement virtuel + dependances =="
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt" gunicorn

echo "== 4/7 Service systemd (web) =="
cp "$APP_DIR/deploy/invest_tracker.service" /etc/systemd/system/invest_tracker.service
systemctl daemon-reload
systemctl enable --now invest_tracker

echo "== 5/7 Nginx (reverse proxy port 80) =="
cp "$APP_DIR/deploy/invest_tracker.nginx.conf" /etc/nginx/sites-available/invest_tracker
ln -sf /etc/nginx/sites-available/invest_tracker /etc/nginx/sites-enabled/invest_tracker
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo "== 6/7 Tache planifiee (collecte quotidienne a 4h) =="
cp "$APP_DIR/deploy/invest_tracker.cron" /etc/cron.d/invest_tracker
chmod 644 /etc/cron.d/invest_tracker
systemctl restart cron || true

echo "== 7/7 Verification =="
systemctl status invest_tracker --no-pager || true
echo ""
echo "OK. Site disponible sur : http://$(curl -s ifconfig.me 2>/dev/null || echo 'IP_DU_SERVEUR')"
echo "Logs de collecte : $APP_DIR/data/collect.log"
