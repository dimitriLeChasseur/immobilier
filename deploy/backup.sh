#!/usr/bin/env bash
# Sauvegarde des données qui ne se reconstruisent pas : comptes, droits d'accès, crédits,
# abonnements, marque blanche. Les référentiels publics (ventes, écoles, points d'intérêt…)
# sont exclus : ils se rechargent par ingestion et pèsent plusieurs centaines de Mo.
#
#   sudo ./deploy/backup.sh                 # écrit dans /srv/immo-backups
#   BACKUP_DIR=/mnt/disque ./deploy/backup.sh
#
# Copie hors site : si R2_BUCKET est renseigné dans le .env (avec R2_ACCOUNT_ID,
# R2_ACCESS_KEY_ID et R2_SECRET_ACCESS_KEY), chaque sauvegarde est aussi envoyée sur
# Cloudflare R2. La durée de conservation s'y règle par une règle de cycle de vie du bucket.
#
# Restauration : ./deploy/restore.sh /srv/immo-backups/immo-AAAA-MM-JJ-HHMM.dump
# Récupérer une copie hors site : ./deploy/backup-fetch.sh immo-AAAA-MM-JJ-HHMM.dump
set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-/srv/immo-backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
# Un fichier plus petit que cela ne peut pas contenir les tables attendues.
MIN_BYTES=2048

# Valeur d'un réglage : l'environnement d'abord, sinon le .env du projet.
setting() {
  local name="$1" value="${!1:-}"
  if [[ -z "$value" && -r .env ]]; then
    value="$(grep -E "^${name}=" .env | tail -1 | cut -d= -f2- || true)"
  fi
  printf '%s' "$value"
}

# Envoie le fichier vers Cloudflare R2 (API compatible S3, requête signée par curl), puis
# relit sa taille sur le stockage : un envoi tronqué est une erreur.
upload_offsite() {
  local file="$1" name bucket endpoint key secret url remote_size
  name="$(basename "$file")"
  bucket="$(setting R2_BUCKET)"
  key="$(setting R2_ACCESS_KEY_ID)"
  secret="$(setting R2_SECRET_ACCESS_KEY)"
  endpoint="$(setting R2_ENDPOINT)"
  [[ -n "$endpoint" ]] || endpoint="https://$(setting R2_ACCOUNT_ID).r2.cloudflarestorage.com"
  if [[ -z "$key" || -z "$secret" || "$endpoint" == "https://.r2.cloudflarestorage.com" ]]; then
    echo "Erreur : copie hors site demandée (R2_BUCKET) mais identifiants R2 incomplets." >&2
    return 1
  fi
  url="${endpoint%/}/${bucket}/${name}"
  # Le secret passe par un fichier de configuration lu sur l'entrée standard : il n'apparaît
  # ni dans la liste des processus ni dans les journaux.
  if ! printf 'user = "%s:%s"\n' "$key" "$secret" | curl --silent --show-error --fail \
      --max-time 300 --config - --aws-sigv4 "aws:amz:auto:s3" --upload-file "$file" "$url"; then
    echo "Erreur : envoi hors site de $name impossible." >&2
    return 1
  fi
  remote_size="$(printf 'user = "%s:%s"\n' "$key" "$secret" | curl --silent --fail --head \
      --max-time 60 --config - --aws-sigv4 "aws:amz:auto:s3" "$url" \
      | tr -d '\r' | awk 'tolower($1) == "content-length:" {print $2}')"
  if [[ "$remote_size" != "$(stat -c %s "$file")" ]]; then
    echo "Erreur : copie hors site de $name incomplète (${remote_size:-0} octets reçus)." >&2
    return 1
  fi
}

umask 077
mkdir -p "$BACKUP_DIR"
target="$BACKUP_DIR/immo-$(date +%F-%H%M).dump"
partial="$target.partiel"
trap 'rm -f "$partial"' EXIT

# L'entrée standard est fermée : lancé depuis un script lu sur l'entrée, pg_dump ne doit pas
# en consommer la suite.
docker compose exec -T db pg_dump -U supabase_admin -d postgres --format=custom \
  --table='auth.*' \
  --exclude-table='auth.schema_migrations' \
  --table='immo.audit_entitlements' \
  --table='immo.user_credits' \
  --table='immo.user_subscriptions' \
  --table='immo.user_branding' \
  --table='immo.stripe_events' \
  < /dev/null > "$partial"

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

# Copie hors site : sans elle, la perte du serveur emporte aussi les sauvegardes.
offsite="non configurée"
if [[ -n "$(setting R2_BUCKET)" ]]; then
  upload_offsite "$target"
  offsite="envoyée"
fi
# Rotation : seules les sauvegardes de ce script, plus anciennes que la durée de conservation.
find "$BACKUP_DIR" -maxdepth 1 -name 'immo-*.dump' -type f -mtime "+$KEEP_DAYS" -delete
kept="$(find "$BACKUP_DIR" -maxdepth 1 -name 'immo-*.dump' | wc -l)"
echo "$(date -Is) sauvegarde $target : $size octets, $tables tables, $kept conservée(s), copie hors site $offsite"
