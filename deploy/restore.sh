#!/usr/bin/env bash
# Restaure une sauvegarde produite par deploy/backup.sh.
#
#   sudo ./deploy/restore.sh /srv/immo-backups/immo-AAAA-MM-JJ-HHMM.dump
#
# À lancer sur une installation dont la pile tourne (le schéma existe déjà). Les comptes,
# droits, crédits, abonnements et marques ACTUELS sont remplacés par ceux de la sauvegarde ;
# les référentiels publics ne sont pas touchés. Tout se fait dans une seule transaction :
# en cas d'erreur, la base reste dans son état d'avant.
set -euo pipefail

cd "$(dirname "$0")/.."
dump="${1:?Usage : $0 fichier.dump [--yes]}"
[[ -r "$dump" ]] || { echo "Erreur : fichier illisible : $dump" >&2; exit 1; }

psql() { docker compose exec -T db psql -U supabase_admin -d postgres -v ON_ERROR_STOP=1 "$@"; }

# Tables contenues dans la sauvegarde, sous la forme schéma.table.
tables="$(docker compose exec -T db pg_restore --list < "$dump" \
  | awk '/TABLE DATA/ {print $6 "." $7}' | paste -sd, -)"
[[ -n "$tables" ]] || { echo "Erreur : aucune table dans cette sauvegarde." >&2; exit 1; }

if [[ "${2:-}" != "--yes" ]]; then
  echo "Les données actuelles de ces tables seront remplacées :"
  echo "  ${tables//,/, }"
  read -r -p "Saisissez « restaurer » pour continuer : " answer
  [[ "$answer" == "restaurer" ]] || { echo "Abandon."; exit 1; }
fi

# Vidage et rechargement dans la même transaction ; les déclencheurs sont suspendus pour que
# l'ordre de chargement n'ait pas à suivre les clés étrangères.
{
  echo "BEGIN;"
  echo "SET session_replication_role = replica;"
  echo "TRUNCATE TABLE ${tables} CASCADE;"
  docker compose exec -T db pg_restore --data-only --file=- < "$dump"
  echo "SET session_replication_role = DEFAULT;"
  echo "COMMIT;"
} | psql -q > /dev/null

docker compose restart auth backend > /dev/null
echo "Restauration terminée : $(psql -Atc 'SELECT count(*) FROM auth.users') compte(s)."
