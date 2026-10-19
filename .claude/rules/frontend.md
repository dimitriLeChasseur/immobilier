---
paths:
  - "frontend/src/**"
---

# Frontend

- Les appels réseau passent par `frontend/src/api/` ; un composant ou une vue n'appelle pas
  `fetch` directement.
- Dans l'aperçu, n'importe quelle valeur peut valoir `***LOCKED***` : la tester avec
  `isLocked` (`frontend/src/lib/teaser.ts`) avant de l'afficher ou de calculer avec.
- Les prix s'affichent depuis `frontend/src/lib/pricing.ts` ; aucun montant n'est écrit en
  dur dans un composant.
