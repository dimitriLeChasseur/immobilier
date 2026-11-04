# ADR 0003 — Cache du rapport jugé source par source

- **Statut** : accepté (reconstitué le 04/11/2026 depuis le README)
- **Contexte** : 21 sources de fiabilité inégale ; un rapport doit rester rapide et à jour sans réinterroger tout le monde.
- **Décision** : un rapport complet est conservé 7 jours, un partiel 15 minutes ; la fraîcheur se juge par source (source en échec réinterrogée seule après 15 min, air après 12 h) ; `REPORT_VERSION` incrémenté à tout changement de format.
- **Conséquences** : moins d'appels aux sources (quotas) ; obligation d'incrémenter la version, rappelée par `.claude/rules/sources.md`.
