#!/usr/bin/env bash
# Lance une tâche planifiée, journalise sa sortie et prévient par e-mail si elle échoue.
#
#   ./deploy/run-task.sh "Sauvegarde" /var/log/immo-backup.log ./deploy/backup.sh
#
# L'alerte part par le backend (python -m app.notify) vers ALERT_EMAIL. Si l'envoi lui-même
# échoue, l'erreur reste dans le journal : la tâche n'est jamais relancée d'ici.
set -uo pipefail

cd "$(dirname "$0")/.."
name="${1:?Usage : $0 nom journal commande…}"
log="${2:?journal manquant}"
shift 2

output="$(mktemp)"
trap 'rm -f "$output"' EXIT

{
  echo "=== $(date -Is) $name"
  "$@" < /dev/null
} > "$output" 2>&1
status=$?
cat "$output" >> "$log"

if (( status != 0 )); then
  echo "=== $(date -Is) $name : échec (code $status), envoi de l'alerte" >> "$log"
  tail -n 60 "$output" \
    | docker compose exec -T backend python -m app.notify "$name en échec (code $status)" \
    >> "$log" 2>&1 || echo "=== alerte non envoyée" >> "$log"
fi
exit "$status"
