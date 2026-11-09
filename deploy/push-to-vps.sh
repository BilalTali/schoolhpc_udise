#!/usr/bin/env bash
# Sends the app to the VPS and restarts it (run ON THE MAC, from the project folder):
#   bash deploy/push-to-vps.sh <VPS-IP>
# Builds the web app, copies the code (never .env, data/ or git), installs Python packages, restarts the service.
set -euo pipefail
HOST="${1:?usage: push-to-vps.sh <VPS-IP or name>}"
APP_DIR=/srv/teacher-assist
cd "$(dirname "$0")/.."

(cd frontend && npm run build)
rsync -az --delete \
  --exclude '.git' --exclude '.env' --exclude '.pytest_cache' --exclude '__pycache__' --exclude 'venv' \
  --exclude 'node_modules' --exclude '/data' --exclude 'deploy/*.local' \
  ./ "teacher@${HOST}:${APP_DIR}/"
ssh "teacher@${HOST}" "cd ${APP_DIR} && { [ -x venv/bin/python ] || python3 -m venv venv; } \
  && venv/bin/pip install -q --upgrade pip && venv/bin/pip install -q -r requirements.txt \
  && sudo /usr/bin/systemctl restart teacher-assist && sleep 3 \
  && curl -fsS -o /dev/null -w 'App answers: HTTP %{http_code}\n' http://127.0.0.1:8000/api/v1/access/status"
