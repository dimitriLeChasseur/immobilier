#!/usr/bin/env bash
# Verrouillage réseau du VPS (Contabo, Ubuntu) avec UFW.
#
#   sudo ./deploy/setup_ufw.sh            # applique les règles
#   sudo ./deploy/setup_ufw.sh --dry-run  # affiche ce qui serait fait
#
# Politique : tout le trafic entrant est refusé, sauf SSH (22), HTTP (80) et HTTPS (443).
# Aucun port interne n'est ouvert : Postgres (5432/5433), FastAPI (8000), Supabase Studio
# (3100) et SonarQube (9000) ne sont joignables que depuis le serveur ou par tunnel SSH.
#
# ATTENTION, Docker : un port publié par un conteneur contourne UFW (Docker écrit ses propres
# règles iptables). La protection des ports internes repose donc AUSSI sur docker-compose.yml,
# où ils sont liés à 127.0.0.1 ou non publiés. Ne jamais y écrire "5433:5432" sans "127.0.0.1:".
#
# Le script n'efface pas les règles existantes (pas de `ufw reset`) : il est rejouable et
# n'interrompt pas les autres services déjà autorisés sur ce serveur.
set -euo pipefail

SSH_PORT=22
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

run() {
  if (( DRY_RUN )); then
    printf '[simulation] %s\n' "$*"
  else
    "$@"
  fi
}

if (( ! DRY_RUN )) && [[ "$(id -u)" -ne 0 ]]; then
  echo "Erreur : à lancer avec sudo (ou --dry-run pour simuler)." >&2
  exit 1
fi

command -v ufw >/dev/null || { echo "Erreur : ufw n'est pas installé (apt install ufw)." >&2; exit 1; }

# Garde-fou anti-verrouillage : si sshd n'écoute pas sur le port 22, activer le pare-feu
# couperait l'accès au serveur.
if command -v ss >/dev/null && ! ss -H -tln 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]${SSH_PORT}\$"; then
  echo "Erreur : aucun service n'écoute sur le port ${SSH_PORT}. Si SSH utilise un autre port," >&2
  echo "adaptez SSH_PORT dans ce script avant de l'exécuter, sous peine de perdre l'accès." >&2
  exit 1
fi

run ufw default deny incoming
run ufw default allow outgoing

# SSH est autorisé AVANT l'activation du pare-feu.
run ufw allow "${SSH_PORT}/tcp" comment 'SSH'
run ufw allow 80/tcp comment 'HTTP (redirection et certificats)'
run ufw allow 443/tcp comment 'HTTPS'
# HTTP/3 (facultatif) : décommenter pour l'activer, sinon les clients utilisent HTTP/2.
# run ufw allow 443/udp comment 'HTTP/3'

run ufw --force enable

if (( ! DRY_RUN )); then
  ufw status verbose
  echo
  echo "Ports en écoute hors boucle locale (seuls 22, 80 et 443 doivent apparaître) :"
  ss -H -tln | awk '$4 !~ /^(127\.|\[::1\])/ {print "  " $4}' | sort -u
fi
