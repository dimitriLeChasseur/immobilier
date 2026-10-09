#!/usr/bin/env bash
# Sauvegarde des données qui ne se reconstruisent pas : comptes, droits d'accès, crédits,
# abonnements, marque blanche. Les référentiels publics (ventes, écoles, points d'intérêt…)
# sont exclus : ils se rechargent par ingestion et pèsent plusieurs centaines de Mo.
#
#   sudo ./deploy/backup.sh                 # écrit dans /srv/immo-backups
#   BACKUP_DIR=/mnt/disque ./deploy/backup.sh
#
# Restauration : ./deploy/restore.sh /srv/immo-backups/immo-AAAA-MM-JJ-HHMM.dump
set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-/srv/immo-backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
# Un fichier plus petit que cela ne peut pas contenir les tables attendues.
MIN_BYTES=2048

umask 077
mkdir -p "$BACKUP_DIR"
target="$BACKUP_DIR/immo-$(date +%F-%H%M).dump"
partial="$target.partiel"
trap 'rm -f "$partial"' EXIT

docker compose exec -T db pg_dump -U supabase_admin -d postgres --format=custom \
  --table='auth.*' \
  --exclude-table='auth.schema_migrations' \
  --table='immo.audit_entitlements' \
  --table='immo.user_credits' \
  --table='immo.user_subscriptions' \
  --table='immo.user_branding' \
  --table='immo.stripe_events' \
  > "$partial"

# Une sauvegarde illisible est pire qu'une sauvegarde absente : on la relit avant de la garder.
size="$(stat -c %s "$partial")"
if (( size < MIN_BYTES )); then
  echo "Erreur : sauvegarde de $size octets, trop petite pour être valable." >&2
  exit 1
fi
tables="$(docker compose exec -T db pg_restore --list < "$partial" | grep -c 'TABLE DATA' || true)"
if (( tables < 5 )); then
  echo "Erreur : sauvegarde illisible ou incomplète ($tables tables de données)." >&2
  exit 1
fi

mv "$partial" "$target"
trap - EXIT
# Rotation : seules les sauvegardes de ce script, plus anciennes que la durée de conservation.
find "$BACKUP_DIR" -maxdepth 1 -name 'immo-*.dump' -type f -mtime "+$KEEP_DAYS" -delete
echo "$(date -Is) sauvegarde $target : $size octets, $tables tables, $(find "$BACKUP_DIR" -maxdepth 1 -name 'immo-*.dump' | wc -l) conservée(s)"
