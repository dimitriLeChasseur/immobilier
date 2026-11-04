# Conformité — Audit-immobilier

| Sujet | État | Action |
| --- | --- | --- |
| Mentions légales (SIRET, TVA, médiateur) | **Incomplètes** (README, limites connues) | Compléter `frontend/src/lib/legal.ts`, puis indexer les pages légales |
| Paiement en production | Clés de **test** Stripe | Passer en clés de production avec le webhook dédié |
| CGV : rétractation pour un contenu numérique fourni immédiatement | ⚠ | Mention et accord exprès avant paiement |
| RGPD | Registre rédigé (`docs/rgpd.md`) | Valider les durées, publier l'adresse de contact, export des données du compte |
| Licences des sources | Sources citées dans le rapport et le PDF (exigé par les licences, y compris en marque blanche) | Vérifier à chaque nouvelle source (`research`) |
| Encadrement des loyers | Liste codée en dur, vérifiée le 01/08/2026 | Relire à chaque décret |
