---
paths:
  - "infra/db/**"
---

# Schéma de la base

`infra/db/init/init.sql` est rejoué à chaque déploiement. Toute instruction doit être
rejouable (`IF NOT EXISTS`, `CREATE OR REPLACE`, `ON CONFLICT`…). Pas de migrations numérotées.
