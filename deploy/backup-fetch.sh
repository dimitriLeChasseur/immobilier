#!/usr/bin/env bash
# Télécharge une sauvegarde depuis Cloudflare R2, pour la restaurer sur un serveur neuf.
#
#   ./deploy/backup-fetch.sh immo-2026-10-09-0230.dump          # vers le dossier courant
#   ./deploy/backup-fetch.sh immo-2026-10-09-0230.dump /srv/immo-backups
#
# Les noms suivent la date : immo-AAAA-MM-JJ-HHMM.dump (sauvegarde quotidienne à 02 h 30).
# Réglages lus dans l'environnement ou dans le .env : R2_BUCKET, R2_ACCOUNT_ID,
# R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY.
set -euo pipefail

cd "$(dirname "$0")/.."
name="${1:?Usage : $0 immo-AAAA-MM-JJ-HHMM.dump [dossier]}"
[[ "$name" =~ ^immo-[0-9-]+\.dump$ ]] || { echo "Erreur : nom de sauvegarde inattendu." >&2; exit 1; }
destination="${2:-$OLDPWD}"

setting() {
  local value="${!1:-}"
  if [[ -z "$value" && -r .env ]]; then
    value="$(grep -E "^${1}=" .env | tail -1 | cut -d= -f2- || true)"
  fi
  printf '%s' "$value"
}

endpoint="$(setting R2_ENDPOINT)"
[[ -n "$endpoint" ]] || endpoint="https://$(setting R2_ACCOUNT_ID).r2.cloudflarestorage.com"
umask 077
printf 'user = "%s:%s"\n' "$(setting R2_ACCESS_KEY_ID)" "$(setting R2_SECRET_ACCESS_KEY)" \
  | curl --silent --show-error --fail --max-time 300 --config - --aws-sigv4 "aws:amz:auto:s3" \
      --output "$destination/$name" "${endpoint%/}/$(setting R2_BUCKET)/$name"
echo "Sauvegarde récupérée : $destination/$name ($(stat -c %s "$destination/$name") octets)"
