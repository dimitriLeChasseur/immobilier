#!/usr/bin/env bash
# Prépare l'instance SonarQube locale (à lancer une fois, après
# `docker compose --profile quality up -d`) :
#   - remplace le mot de passe admin par défaut ;
#   - crée le projet, un jeton d'analyse et le Quality Gate du projet.
# Écrit SONAR_ADMIN_PASSWORD et SONAR_TOKEN dans .env.
set -euo pipefail

cd "$(dirname "$0")/.."

SONAR_URL="${SONAR_URL:-http://localhost:9000}"
PROJECT_KEY="audit-immobilier"
GATE_NAME="Audit Immobilier"

if grep -q '^SONAR_TOKEN=.\+' .env 2>/dev/null; then
  echo "SONAR_TOKEN est déjà défini dans .env : rien à faire." >&2
  exit 0
fi

set_env() {
  local key="$1" value="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

api() {
  local method="$1" path="$2"
  shift 2
  curl --silent --show-error --fail --user "admin:${password}" --request "$method" "${SONAR_URL}${path}" "$@"
}

# Mot de passe admin : celui de .env s'il existe, sinon on remplace le défaut.
password="$(grep -oP '^SONAR_ADMIN_PASSWORD=\K.+' .env || true)"
if [[ -z "$password" ]]; then
  password="$(openssl rand -hex 16)Aa1!"
  curl --silent --show-error --fail --user admin:admin --request POST \
    "${SONAR_URL}/api/users/change_password" \
    --data-urlencode login=admin \
    --data-urlencode previousPassword=admin \
    --data-urlencode "password=${password}"
  set_env SONAR_ADMIN_PASSWORD "$password"
  echo "Mot de passe admin SonarQube remplacé (voir SONAR_ADMIN_PASSWORD dans .env)."
fi

api POST /api/projects/create --data-urlencode "project=${PROJECT_KEY}" \
  --data-urlencode "name=Audit Immobilier" >/dev/null || true

# Quality Gate : conditions sur l'ensemble du code (et non sur le seul nouveau code).
api POST /api/qualitygates/create --data-urlencode "name=${GATE_NAME}" >/dev/null || true
add_condition() {
  api POST /api/qualitygates/create_condition --data-urlencode "gateName=${GATE_NAME}" \
    --data-urlencode "metric=$1" --data-urlencode "op=$2" --data-urlencode "error=$3" >/dev/null || true
}
add_condition vulnerabilities GT 0
# 100 % des Security Hotspots revus = aucun hotspot laissé ouvert.
add_condition security_hotspots_reviewed LT 100
add_condition bugs GT 0
add_condition duplicated_lines_density GT 5
add_condition security_rating GT 1
add_condition reliability_rating GT 1

# Le modèle par défaut impose 80 % de couverture sur le nouveau code : hors des exigences
# du projet, cette condition est retirée.
coverage_condition="$(api GET "/api/qualitygates/show?name=${GATE_NAME// /%20}" \
  | grep -oP '"id":"\K[^"]+(?=","metric":"new_coverage")' || true)"
if [[ -n "$coverage_condition" ]]; then
  api POST /api/qualitygates/delete_condition --data-urlencode "id=${coverage_condition}" >/dev/null
fi
api POST /api/qualitygates/select --data-urlencode "gateName=${GATE_NAME}" \
  --data-urlencode "projectKey=${PROJECT_KEY}" >/dev/null

token="$(api POST /api/user_tokens/generate --data-urlencode "name=analyse-locale-$(date +%s)" \
  | sed -E 's/.*"token":"([^"]+)".*/\1/')"
set_env SONAR_TOKEN "$token"
echo "Projet, Quality Gate et jeton prêts. Lancez ./scripts/sonar-scan.sh"
