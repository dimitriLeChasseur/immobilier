# Politique de mise à jour des dépendances

| Situation | Délai | Comment |
| --- | --- | --- |
| Faille critique ou haute dans un composant **exposé à Internet** (framework web, n8n, Caddy, aiohttp, client HTTP) | **72 h** | Mise à jour ciblée, tests, déploiement ; note dans `CHANGELOG.md` (section Sécurité) |
| Faille critique ou haute non exposée (outil de build, script local) | 2 semaines | Lot de mises à jour |
| Faille moyenne ou basse | Revue mensuelle | Lot de mises à jour |
| Version majeure sans faille | Quand un besoin le justifie | Branche dédiée, lecture des notes de migration (Context7), tests complets |

Règles :
1. **Versions figées** : lockfile versionné (`uv.lock`, `package-lock.json`, `bun.lock`) ; images Docker par version (et empreinte quand possible) ; actions GitHub par SHA.
2. **Contrôle automatique** : `npm audit --omit=dev --audit-level=high` et `pip-audit` en CI ; Dependabot (alertes de sécurité) activé sur chaque dépôt.
3. **Une nouvelle dépendance** se justifie : la bibliothèque standard ou une dépendance déjà installée ne suffit pas ; licence compatible ; projet maintenu (dernière version < 12 mois) ; nombre de dépendances transitives raisonnable.
4. **Pas de dépendance d'outil en production** : CLI, types, outils de génération en `devDependencies` / groupe `dev`.
5. Toute mise à jour passe par une PR avec CI verte ; jamais directement sur le serveur.
