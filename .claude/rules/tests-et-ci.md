---
paths:
  - "backend/tests/**"
  - "backend/pyproject.toml"
  - "frontend/tests/**"
  - "frontend/e2e/**"
  - "frontend/vite.config.ts"
  - ".github/**"
---

# Tests et intégration continue

- Ne jamais baisser un seuil de couverture (les deux `--cov-fail-under` de `ci.yml`, `thresholds`
  dans `frontend/vite.config.ts`), ni ignorer, désactiver ou affaiblir un test pour faire
  passer la CI : corriger le code, ou signaler le blocage à l'utilisateur. Quand la couverture
  dépasse nettement un seuil, le remonter à environ un point sous le niveau mesuré par la CI
  (journal du job), pas en local : un `.env` local change la couverture du frontend.
- Un test se justifie par un comportement à protéger, jamais par la couverture seule : pas de
  test qui exécute du code sans rien vérifier de ce qu'il produit.
- Chaque action GitHub est épinglée par empreinte de commit complète (`@<sha>`), avec la
  version en commentaire ; Dependabot les met à jour.
- Un échec du parcours e2e bloque la mise en ligne du site : il se corrige, il ne se contourne
  pas.
