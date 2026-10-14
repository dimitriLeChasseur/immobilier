# Audit Immobilier : consignes pour les agents

Une adresse française → une vingtaine de sources publiques interrogées en parallèle → un
rapport (tableau de bord et PDF). Aperçu gratuit, audit complet payant (à l'unité, pack, Pro).
Le `README.md` décrit l'architecture, les variables et l'exploitation : le lire avant toute
intervention qui sort d'un seul fichier.

## Règles du projet

- **Aucun service payant.** Projet autofinancé : pas d'API, d'hébergement ni d'outil payant
  (SonarQube reste local, pas de SonarQube Cloud). Proposer une source gratuite et ouverte.
- **Français partout** : commentaires, docstrings, messages d'erreur, textes du site,
  messages de commit. Les identifiants de code restent en anglais, sauf les noms de source et
  les clés des données renvoyées (`quartier`, `taxe_fonciere`…), qui font partie du contrat
  de l'API.
- **Densité de commentaires** : un commentaire dit *pourquoi*, pas *quoi*. Suivre le style du
  fichier voisin.
- **Masquage côté serveur.** Toute valeur payante est remplacée par `***LOCKED***` dans
  `backend/app/services/teaser.py` (liste blanche par source : un nouveau champ est masqué par
  défaut). Le flou du frontend n'est qu'un habillage : ne jamais compter dessus.
- **Prix fixés côté serveur** (`backend/app/services/billing.py`, `OFFERS`) ; le frontend
  (`frontend/src/lib/pricing.ts`, `frontend/index.html` pour les données structurées)
  ne fait que les afficher. Changer un prix, c'est changer ces trois endroits et les tests.
- **Format du rapport modifié** (champ ajouté, renommé, retiré) : incrémenter
  `report_version` dans `backend/app/core/config.py`, sinon le cache sert l'ancien format
  pendant sept jours.
- **Schéma** : `infra/db/init/init.sql` est rejoué à chaque déploiement. Toute instruction doit
  être rejouable (`IF NOT EXISTS`, `CREATE OR REPLACE`…). Pas de migrations numérotées.
- **Secrets** : jamais dans le dépôt ni dans une sortie affichée. `.env` n'est pas versionné ;
  ce qui commence par `VITE_` finit dans le JavaScript public.
- **Réseau** : seul Caddy publie des ports. Un port interne se publie avec le préfixe
  `127.0.0.1:` (Docker contourne UFW).

## Commandes

```bash
# Backend (depuis backend/)
uv run pytest                       # tests unitaires ; les tests SQL sont ignorés sans base
uv run ruff check app tests && uv run mypy app tests

# Frontend (depuis frontend/)
npm run test && npm run typecheck && npm run lint && npm run build
npm run e2e                         # parcours d'achat ; pile Docker démarrée

# Pile locale (depuis la racine)
docker compose up -d --build        # http://localhost
```

Tests SQL sur une vraie base et commande d'intégration complète : section « Tests et
qualité » du README. La CI (`.github/workflows/ci.yml`) impose des seuils de couverture
(`--cov-fail-under` dans la commande pytest, `thresholds` dans `frontend/vite.config.ts`).

## Avant de rendre la main

1. Les contrôles ci-dessus passent des deux côtés concernés.
2. Un comportement nouveau a son test ; une correction de bug a un test qui échouait avant.
3. Le README est à jour si une commande, une variable ou une procédure a changé.
4. Ne pas commiter ni pousser sans que l'utilisateur l'ait demandé. Un push sur `main` met le
   site en ligne une fois la CI passée.

## Skills du projet (`.claude/skills/`)

| Skill | Quand |
|---|---|
| `ajouter-une-source` | Brancher une nouvelle source de données, ou un nouveau champ visible dans le rapport |
| `mise-en-production` | Pousser, déployer le backend et vérifier le site en ligne (sur demande explicite) |
| `diagnosing-bugs` | Bug difficile, régression, lenteur : boucle de reproduction avant toute hypothèse |
| `tdd` | Développement guidé par les tests (paiement, droits d'accès, quotas) |
| `codebase-design` | Vocabulaire et principes pour découper un module |
| `improve-codebase-architecture` | Revue d'architecture à la demande (`/improve-codebase-architecture`) |
| `domain-modeling`, `grilling` | Glossaire, ADR et questions de conception, appelés par la précédente |
| `wizard` | Script guidé pour une procédure que seul l'humain peut faire (tableaux de bord, clés) |

Les skills génériques viennent de [mattpocock/skills](https://github.com/mattpocock/skills)
(licence MIT), commit `49dd158d1076134a641b33efb035946536778336`, sans les fichiers
`agents/` propres à Codex. Elles sont rédigées en anglais : répondre quand même en
français. Pour les mettre à jour, recopier les dossiers depuis un commit précis et relire
le diff avant de commiter. La commande `/code-review` utilisée ici est celle de Claude Code,
pas celle de ce dépôt.
