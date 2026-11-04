# Contrat d'API — Audit-immobilier

> Généré depuis `backend/app/api/routers/` le 04/11/2026 (méthode, chemin, dépendances FastAPI, première ligne de la docstring). Base en production : `https://api.audit-immobilier.fr`. Les réponses sont décrites par les schémas pydantic de `backend/app/schemas/`. Toute modification d'une forme de réponse est un changement de contrat : mettre à jour ce fichier, le front (`frontend/src/api/`) et incrémenter `REPORT_VERSION` si le rapport change.

| Méthode | Chemin | Protections | Rôle |
| --- | --- | --- | --- |
| GET | `/api/v1/account/audits` | enforce_rate_limit | Adresses que l'utilisateur a débloquées, la plus récente d'abord. |
| GET | `/api/v1/account/history` | enforce_rate_limit | Rapports complets consultés par l'utilisateur, le plus récent d'abord. |
| DELETE | `/api/v1/account` | enforce_rate_limit | Supprime le compte et tout ce qui lui est rattaché ; l'abonnement est arrêté d'abord. |
| GET | `/api/v1/account/branding` | enforce_rate_limit | Marque blanche de l'abonné ; rien pour un compte sans abonnement actif. |
| PUT | `/api/v1/account/branding` | enforce_rate_limit | Enregistre le nom et le logo repris en tête des rapports PDF. |
| DELETE | `/api/v1/account/branding` | enforce_rate_limit |  |
| GET | `/api/v1/sources` | — | Noms des sources d'un rapport, pour afficher les squelettes de chargement. |
| GET | `/api/v1/audit` | enforce_rate_limit enforce_anonymous_quota | Rapport d'audit en une seule réponse JSON ; version « teaser » sans droit d'accès. |
| GET | `/api/v1/audit/stream` | enforce_rate_limit enforce_anonymous_quota | Rapport émis pas à pas : `location`, `access`, `source`…, puis `done` ou `error`. |
| GET | `/api/v1/account` | — | Crédits restants et état de l'abonnement de l'utilisateur connecté. |
| POST | `/api/v1/checkout` | enforce_rate_limit | Crée une session Stripe Checkout et renvoie l'adresse de la page de paiement. |
| POST | `/api/v1/billing/portal` | enforce_rate_limit | Adresse du portail Stripe où l'abonné gère ou résilie son abonnement. |
| POST | `/api/v1/unlock` | enforce_rate_limit | Débloque une adresse avec un crédit d'un pack. |
| POST | `/api/v1/stripe/webhook` | — | Évènements envoyés par Stripe. Seule une signature valide est prise en compte. |
| GET | `/api/v1/communes/{code}` | enforce_rate_limit get_commune_service | Chiffres clés d'une commune, désignée par son code INSEE. |
| GET | `/emails/{kind}.html` | — | Gabarit d'un message d'authentification, à la charte du site. |
| GET | `/health` | — | Sonde de vivacité : le processus répond. |
| GET | `/api/health/ready` | — | Sonde de disponibilité : la base et PostGIS sont joignables. |

## Codes d'erreur communs

| Code | Sens |
| --- | --- |
| 401 | Jeton de session absent, invalide ou expiré (un jeton présent mais invalide est refusé, jamais ignoré) |
| 402 / 403 | Droit absent sur l'adresse ou abonnement inactif ⚠ (vérifier le code exact par route) |
| 429 | Limite de débit ou quota anonyme atteint (en-tête `Retry-After`) |
| 503 | Paiement non configuré (clés Stripe absentes) |

## Flux SSE `/api/v1/audit/stream`

Événements dans l'ordre : `location`, `access`, `source` (un par source, au fil de l'eau), puis `done` ou `error`. Une source en échec n'interrompt pas le flux : le rapport final porte `is_partial` et `failed_sources`.
