#!/usr/bin/env bash
# Génère les rapports de couverture puis lance l'analyse SonarQube.
# Prérequis : docker compose --profile quality up -d, puis ./scripts/sonar-setup.sh
set -euo pipefail

cd "$(dirname "$0")/.."

token="$(grep -oP '^SONAR_TOKEN=\K.+' .env || true)"
if [[ -z "$token" ]]; then
  echo "SONAR_TOKEN absent de .env : lancez d'abord ./scripts/sonar-setup.sh" >&2
  exit 1
fi

echo "== Couverture backend"
(
  cd backend
  DATABASE_URL=postgresql://test:test@localhost/test SUPABASE_JWT_SECRET=test \
    uv run pytest --quiet --cov=app --cov-report=xml:coverage.xml
  # Chemins relatifs à la racine du dépôt, telle que la voit le scanner.
  sed -i -e 's|filename="|filename="backend/app/|' -e 's|<source>.*</source>|<source>.</source>|' coverage.xml
)

echo "== Couverture frontend"
(
  cd frontend
  npx vitest run --coverage --coverage.provider=v8 --coverage.reporter=lcov \
    --coverage.include='src/**' --silent
  sed -i 's|^SF:src/|SF:frontend/src/|' coverage/lcov.info
)

echo "== Analyse SonarQube"
# data/ (fichiers Postgres, illisibles pour le scanner) est masqué par un tmpfs vide.
docker run --rm \
  --network immo_quality \
  --user "$(id -u):$(id -g)" \
  --env SONAR_HOST_URL=http://sonarqube:9000 \
  --env SONAR_TOKEN="$token" \
  --env SONAR_USER_HOME=/tmp/sonar \
  --volume "$PWD:/usr/src" \
  --tmpfs /usr/src/data \
  sonarsource/sonar-scanner-cli:latest
