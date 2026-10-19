---
paths:
  - "docker-compose.yml"
  - "deploy/**"
  - "infra/caddy/**"
---

# Conteneurs et réseau

- Seul Caddy publie des ports. Un port interne se publie avec le préfixe `127.0.0.1:` :
  Docker contourne UFW, un port publié sans préfixe est ouvert sur Internet.
- Chaque image porte une version exacte, jamais `latest` ni une version flottante : Dependabot
  propose les montées de version.
