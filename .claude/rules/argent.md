---
paths:
  - "backend/app/services/billing.py"
  - "backend/app/services/accounts.py"
  - "backend/app/api/routers/billing.py"
  - "backend/app/api/routers/account.py"
  - "backend/tests/test_billing.py"
  - "backend/tests/test_integration_billing_sql.py"
  - "frontend/src/lib/pricing.ts"
  - "frontend/src/api/billing.ts"
  - "frontend/index.html"
  - "frontend/src/views/PricingView.vue"
  - "frontend/src/router.ts"
---

# Chemin de l'argent

- Les prix sont fixés côté serveur (`OFFERS` dans `billing.py`). `frontend/src/lib/pricing.ts`
  et les données structurées de `frontend/index.html` ne font que les afficher. Changer un
  prix, c'est changer ces trois endroits et les tests. Tout autre texte qui cite un prix le
  lit dans `pricing.ts` (`tests/pricing-source.test.ts` le vérifie pour la page tarifs).
- Le navigateur ne peut pas ouvrir un droit : seul un évènement Stripe dont la signature est
  vérifiée crée un droit, des crédits ou un abonnement. Aucune route ne doit accorder un accès
  sur la seule parole du client (paramètre de retour de paiement, identifiant de session…).
- Tout changement des droits, crédits, abonnements, remboursements ou du plafond Pro a son
  test unitaire et, s'il touche au SQL, son cas dans `test_integration_billing_sql.py`
  (procédure dans la section « Tests et qualité » du README).
