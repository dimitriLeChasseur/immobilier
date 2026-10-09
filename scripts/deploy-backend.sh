#!/usr/bin/env bash
# Met à jour le backend sur le serveur à partir du commit courant.
#
#   ./scripts/deploy-backend.sh root@169.58.58.27
#
# Le code part de ce poste (aucun identifiant GitHub sur le serveur), le .env du serveur n'est
# jamais touché, et le schéma est réappliqué : init.sql est rejouable.
set -euo pipefail

cd "$(dirname "$0")/.."
REMOTE="${1:?Usage : $0 utilisateur@serveur}"
APP_DIR="${APP_DIR:-/opt/project-immobilier}"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Erreur : des modifications ne sont pas commitées ; seul le dernier commit serait envoyé." >&2
  exit 1
fi
commit="$(git rev-parse --short HEAD)"
echo "Envoi du commit $commit vers $REMOTE:$APP_DIR"
git archive HEAD | ssh "$REMOTE" "tar -x -C '$APP_DIR'"

ssh "$REMOTE" "bash -s" <<REMOTE_SCRIPT
set -euo pipefail
cd '$APP_DIR'
docker compose up -d --build
docker compose exec -T db psql -U supabase_admin -d postgres -v ON_ERROR_STOP=1 -q \
  -f /docker-entrypoint-initdb.d/init-scripts/99-zzz-init.sql
docker compose exec -T backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready', timeout=10).read().decode())"
echo "$commit" > .deployed-commit
REMOTE_SCRIPT
echo "Déployé : $commit"
