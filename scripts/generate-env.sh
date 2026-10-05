#!/usr/bin/env bash
# Crée .env à partir de .env.example en générant tous les secrets,
# y compris les clés d'API Supabase (JWT HS256 signés avec JWT_SECRET).
# Refuse d'écraser un .env existant : les secrets sont liés aux données en base.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -e .env ]]; then
  echo "Erreur : .env existe déjà. Supprimez-le explicitement pour régénérer." >&2
  exit 1
fi

command -v openssl >/dev/null || { echo "Erreur : openssl est requis." >&2; exit 1; }

rand_hex() { openssl rand -hex "$1"; }

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

# sign_jwt <role> <secret> : JWT HS256 valable 10 ans
sign_jwt() {
  local role="$1" secret="$2" now exp header payload signature
  now="$(date +%s)"
  exp="$((now + 10 * 365 * 24 * 3600))"
  header="$(printf '%s' '{"alg":"HS256","typ":"JWT"}' | b64url)"
  payload="$(printf '{"role":"%s","iss":"supabase","iat":%s,"exp":%s}' "$role" "$now" "$exp" | b64url)"
  signature="$(printf '%s' "${header}.${payload}" | openssl dgst -sha256 -hmac "$secret" -binary | b64url)"
  printf '%s.%s.%s' "$header" "$payload" "$signature"
}

jwt_secret="$(rand_hex 32)"

declare -A secrets=(
  [POSTGRES_PASSWORD]="$(rand_hex 24)"
  [IMMO_APP_DB_PASSWORD]="$(rand_hex 24)"
  [JWT_SECRET]="$jwt_secret"
  [ANON_KEY]="$(sign_jwt anon "$jwt_secret")"
  [SERVICE_ROLE_KEY]="$(sign_jwt service_role "$jwt_secret")"
  [PG_META_CRYPTO_KEY]="$(rand_hex 24)"
  [SONAR_DB_PASSWORD]="$(rand_hex 24)"
)

umask 077
cp .env.example .env
for key in "${!secrets[@]}"; do
  sed -i "s|^${key}=.*|${key}=${secrets[$key]}|" .env
done

echo ".env créé (droits 600). Ajustez SITE_ADDRESS, PUBLIC_URL, SITE_URL et CORS_ALLOWED_ORIGINS."
