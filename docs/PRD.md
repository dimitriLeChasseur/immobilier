# PRD — Audit-immobilier (audit-immobilier.fr)

> Version 1.0 (04/11/2026), reconstituée à partir du code (`4fd1e64`), du README et du glossaire. Le vocabulaire suit `GLOSSARY.md`. ⚠ = à confirmer.

## 1. Vision

Avant de faire une offre sur un logement, tout vérifier sur **une adresse** en une minute : prix des ventes voisines, bâtiment, DPE, risques, bruit, air, permis de construire alentour, écoles, transports, profil du quartier, règles de location. Une vingtaine de sources publiques, un **rapport** clair et un PDF à apporter à la seconde visite.

## 2. Clients

| Persona | Besoin | Offre |
| --- | --- | --- |
| Acheteur particulier | Vérifier un bien avant l'offre | **Contre-Visite** 2,99 € TTC (une adresse) |
| Investisseur | Comparer plusieurs biens, rendement | **Pack Investisseur** 19,99 € TTC (crédits d'adresses) |
| Professionnel (agent, chasseur, CGP) | Rapports à sa marque pour ses clients | **Pro** 49 € HT/mois, 150 adresses par jour, marque blanche |
| Visiteur | Comprendre la commune | **Aperçu** gratuit, sans compte, fiches communales |

## 3. Fonctionnalités existantes

| Domaine | Fonctionnalité |
| --- | --- |
| Rapport | 21 sources en parallèle, flux SSE (`/api/v1/audit/stream`), dégradation gracieuse (`is_partial`, `failed_sources`), synthèse (`insights.py`) |
| Aperçu | Masquage serveur par liste blanche (`teaser.py`, `***LOCKED***`), accroches, chiffres de commune en clair |
| Rapport d'exemple | Adresse `DEMO_ADDRESS_ID` servie complète à tous |
| Compte | Supabase Auth (mot de passe, Google), historique des rapports, suppression en libre-service |
| Paiement | Stripe Checkout (unité, pack, Pro), portail, remboursement intégral qui retire les droits, TVA Pro |
| Pro | Marque blanche (nom, logo PNG/JPEG ≤ 200 Ko) sur le PDF, plafond de 150 adresses par jour |
| SEO | Fiches communales prérendues, sitemaps |
| Données | Ingestion mensuelle (OSM, bruit Lden 65 départements, INSEE, Sitadel), millésimes datés |
| Qualité | 51 fichiers de tests, couverture minimale imposée en CI, test de fumée nocturne, surveillance externe |

## 4. Exigences non fonctionnelles

| Exigence | Cible |
| --- | --- |
| Temps de génération d'un rapport non caché | < 10 s, premières sources visibles < 2 s (SSE) |
| Délai par source | 9 s, coupe-circuit |
| Cache | Rapport complet 7 jours, partiel 15 min, air 12 h ; `REPORT_VERSION` incrémenté à chaque changement de format |
| Sécurité | Masquage côté serveur, RLS, rôle `immo_app` sans DDL, seul Caddy exposé |
| Coût | Aucun service payant (règle du projet) |
| Conformité | CGV, mentions légales (SIRET, TVA, médiateur à compléter ⚠), RGPD (`docs/rgpd.md`), licences des sources citées |

## 5. Indicateurs

Aperçus générés, conversion aperçu → achat, panier moyen, abonnés Pro actifs et adresses par abonné, taux de rapports partiels par source, temps de génération p95, remboursements.

## 6. Feuille de route proposée

| Priorité | Sujet |
| --- | --- |
| P0 | Clés Stripe de production et webhook ; mentions légales complètes (limites connues du README) |
| P0 | Correctifs de l'audit (certifi, opentelemetry, `--forwarded-allow-ips`, timeouts, CSP) |
| P1 | Quotas et limitation de débit persistants (PostgreSQL) avant un second worker |
| P1 | Turnstile activé à l'inscription |
| P1 | Surveillance applicative : erreurs et temps de réponse (aujourd'hui seulement la disponibilité) |
| P2 | Bruit : départements manquants (Bouches-du-Rhône, Gironde, Nord, Haute-Garonne, Bas-Rhin) dès qu'un flux est publié |
| P2 | Comparateur de 2 à 4 adresses pour le Pack Investisseur |
| P2 | Agents de l'essaim : `immo-qa` (Stripe en mode test), `immo-metriques` (revue hebdo) |
