#!/usr/bin/env bash
# Installe les tâches planifiées du serveur dans /etc/cron.d/audit-immobilier.
# Rejouable : le fichier est réécrit à chaque exécution.
#
#   sudo ./deploy/install-cron.sh            # installe
#   ./deploy/install-cron.sh --dry-run       # affiche sans rien écrire
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET=/etc/cron.d/audit-immobilier
UV="$(command -v uv || echo /usr/local/bin/uv)"

content="$(cat <<CRON
# Audit Immobilier : tâches planifiées (généré par deploy/install-cron.sh, ne pas éditer).
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Sauvegarde quotidienne des comptes, droits et abonnements.
30 2 * * * root $APP_DIR/deploy/backup.sh >> /var/log/immo-backup.log 2>&1
# Test de fumée : les vraies sources répondent-elles toujours comme attendu ?
0 3 * * * root cd $APP_DIR && docker compose exec -T backend python -m app.smoke >> /var/log/immo-smoke.log 2>&1
# Purge des rapports expirés du cache.
15 3 * * * root cd $APP_DIR && docker compose exec -T db psql -U supabase_admin -d postgres -qAtc "SELECT immo.purge_expired_reports()" >> /var/log/immo-cache.log 2>&1
# Cartes de bruit : le 2 de chaque mois.
0 4 2 * * root cd $APP_DIR && $UV run scripts/ingest_bruit_lden.py >> /var/log/immo-bruit.log 2>&1
# Points d'intérêt OpenStreetMap : le 3 de chaque mois.
0 4 3 * * root cd $APP_DIR && $UV run scripts/ingest_osm_poi.py >> /var/log/immo-osm.log 2>&1
# Permis de construire : le 5 de chaque mois.
0 4 5 * * root cd $APP_DIR && docker compose run --rm -T backend python -m app.ingestion sitadel >> /var/log/immo-ingestion.log 2>&1
# Autres référentiels (délinquance, taxe foncière, IPS, IRIS, fibre) : chaque trimestre.
0 5 6 1,4,7,10 * root cd $APP_DIR && docker compose run --rm -T backend python -m app.ingestion ssmsi dgfip ips iris arcep >> /var/log/immo-ingestion.log 2>&1
CRON
)"

if [[ "${1:-}" == "--dry-run" ]]; then
  printf '%s\n' "$content"
  exit 0
fi
[[ $EUID -eq 0 ]] || { echo "Erreur : à lancer en root (sudo)." >&2; exit 1; }
printf '%s\n' "$content" > "$TARGET"
chmod 644 "$TARGET"
echo "Tâches planifiées installées dans $TARGET :"
grep -c '^[0-9]' "$TARGET"
