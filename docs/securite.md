# Sécurité — Audit-immobilier

Le README (section Architecture, « Sécurité des données », « Réseau ») et `.claude/rules/` décrivent déjà les protections : masquage serveur, RLS, rôle sans DDL, Caddy seul exposé, JWT strict, Stripe signé, quotas.

## Modèle de menace résumé

| Menace | Parade en place | À faire |
| --- | --- | --- |
| Lire un rapport complet sans payer | Masquage serveur par liste blanche, droit par adresse en base | Test de non-régression à chaque nouveau champ (déjà dans la skill `ajouter-une-source`) |
| Abuser des sources publiques via l'API | Limite par IP, quota anonyme, quota par source | Restreindre `--forwarded-allow-ips` à Caddy ; quotas persistants avant un second worker |
| Fraude au paiement / rejeu du webhook | Signature avec horodatage | — |
| Compte Pro partagé | Plafond de 150 adresses par jour | Alerte si plafond atteint plusieurs jours de suite |
| Logo malveillant (marque blanche) | Contrôle du contenu réel, PNG/JPEG seulement, pas de SVG | — |
| Exposition d'un service interne | Ports sur `127.0.0.1`, contrôle `ss` du runbook VPS 2 | Ne jamais lancer `deploy/setup_ufw.sh` sur le VPS 2 (ouvre le 80) |
| Dépendances vulnérables | `securite.yml` (npm audit) | certifi, opentelemetry à mettre à jour ; `pip-audit` en CI |
| Absence de CSP | — | CSP dans les en-têtes du front et `default-src 'none'` sur l'API |
