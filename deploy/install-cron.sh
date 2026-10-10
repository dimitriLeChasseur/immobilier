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
RUN="$APP_DIR/deploy/run-task.sh"

content="$(cat <<CRON
# Audit Immobilier : tâches planifiées (généré par deploy/install-cron.sh, ne pas éditer).
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Chaque tâche passe par run-task.sh : sa sortie est journalisée et un échec déclenche un e-mail.
# Sauvegarde quotidienne des comptes, droits et abonnements.
30 2 * * * root $RUN "Sauvegarde" /var/log/immo-backup.log ./deploy/backup.sh
# Test de fumée : les vraies sources répondent-elles toujours comme attendu ?
0 3 * * * root $RUN "Test de fumée" /var/log/immo-smoke.log docker compose exec -T backend python -m app.smoke
# Purge des rapports expirés du cache.
15 3 * * * root $RUN "Purge du cache" /var/log/immo-cache.log docker compose exec -T db psql -U supabase_admin -d postgres -qAtc "SELECT immo.purge_expired_reports()"
# Cartes de bruit : le 2 de chaque mois.
0 4 2 * * root $RUN "Ingestion du bruit" /var/log/immo-bruit.log $UV run scripts/ingest_bruit_lden.py
# Points d'intérêt OpenStreetMap : le 3 de chaque mois.
0 4 3 * * root $RUN "Ingestion des points d'intérêt" /var/log/immo-osm.log $UV run scripts/ingest_osm_poi.py
# Permis de construire : le 5 de chaque mois.
0 4 5 * * root $RUN "Ingestion des permis" /var/log/immo-ingestion.log docker compose run --rm -T backend python -m app.ingestion sitadel
# Autres référentiels (délinquance, taxe foncière, IPS, IRIS, fibre, revenus, population,
# quartiers prioritaires) : chaque trimestre.
0 5 6 1,4,7,10 * root $RUN "Ingestion des référentiels" /var/log/immo-ingestion.log docker compose run --rm -T backend python -m app.ingestion ssmsi dgfip ips iris arcep loyers zone_tendue carte_scolaire filosofi filosofi_communes population qpv
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
