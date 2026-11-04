# Revue mensuelle de sécurité et d'exploitation — <mois>

> 30 minutes, le premier lundi du mois. Cocher, noter les écarts, ouvrir une issue par action.

## Dépendances
- [ ] `npm audit --omit=dev` et `pip-audit` (ou `uv export | pip-audit`) : aucune vulnérabilité haute ou critique
- [ ] Images Docker : versions à jour (Postgres, Caddy, Ollama, n8n…), avis de sécurité lus
- [ ] Actions GitHub : épinglées par SHA, Dependabot ou Renovate traités

## Accès et secrets
- [ ] Inventaire des secrets (`docs/secrets.md`) à jour ; rotation des secrets de plus de 12 mois
- [ ] Comptes et clés d'accès inutilisés supprimés (Stripe, Supabase, Cloudflare, GitHub, VPS)
- [ ] SSH : clés autorisées revues sur chaque VPS

## Exposition
- [ ] Ports publics : seul 443 (`ss -tlnH` sur chaque VPS)
- [ ] En-têtes de sécurité du site (securityheaders.com ≥ A)
- [ ] Certificats : échéance > 30 jours

## Sauvegardes
- [ ] Dernière sauvegarde réussie < 24 h
- [ ] **Restauration testée** ce trimestre (date : ____) sur une machine ou une base de test

## Supervision
- [ ] Alertes d'échec et de silence reçues ce mois-ci : toutes expliquées
- [ ] Post-mortems du mois écrits et actions suivies

## Données personnelles
- [ ] Purges prévues par le registre RGPD exécutées
- [ ] Demandes d'accès ou de suppression traitées sous 30 jours
