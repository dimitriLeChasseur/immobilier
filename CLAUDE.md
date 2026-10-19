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
- **Le plus petit changement complet.** Lire le code et repérer tout ce que le changement
  touche (appelants, tests, configuration) avant d'écrire ; puis réutiliser ce qui existe
  dans le projet, la bibliothèque standard ou une dépendance installée, et n'écrire du code
  neuf qu'en dernier. Ne jamais rogner sur la validation aux frontières, les erreurs qui
  évitent une perte de données, la sécurité, l'accessibilité ni ce qui a été demandé.
  Terminer en disant ce qui n'a pas été fait ou vérifié.
- **Densité de commentaires** : un commentaire dit *pourquoi*, pas *quoi*. Suivre le style du
  fichier voisin.
- **Secrets** : jamais dans le dépôt ni dans une sortie affichée. `.env` n'est pas versionné ;
  ce qui commence par `VITE_` finit dans le JavaScript public.

Les règles propres à une partie du code sont dans `.claude/rules/` et se chargent quand on
touche les fichiers concernés : aperçu et masquage, chemin de l'argent et prix, sources de
données et `report_version`, schéma SQL, conteneurs et réseau, données datées, frontend,
tests et CI.

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
(`--cov-fail-under` des deux commandes pytest, sans et avec base ; `thresholds` dans
`frontend/vite.config.ts`).

## Avant de rendre la main

1. L'agent `verificateur` rend OK des deux côtés concernés, puis `gardien-du-projet` ne
   signale rien de bloquant sur le diff.
2. Un comportement nouveau a son test ; une correction de bug a un test qui échouait avant.
3. Le README est à jour si une commande, une variable ou une procédure a changé.
4. Ne pas commiter ni pousser sans que l'utilisateur l'ait demandé. Un push sur `main` met le
   site en ligne une fois la CI passée. `/implement` vaut demande de commit, pas de push, et
   le point 1 passe avant son commit.

## Skills du projet (`.claude/skills/`)

| Skill | Quand |
|---|---|
| `ajouter-une-source` | Brancher une nouvelle source de données, ou un nouveau champ visible dans le rapport |
| `mise-en-production` | Pousser, déployer le backend et vérifier le site en ligne (sur demande explicite) |
| `ask-matt` | Ne pas savoir quelle skill utiliser (`/ask-matt`) |
| `grill-with-docs` | Affiner une idée avant de coder ; tient `GLOSSARY.md` et les ADR à jour (`/grill-with-docs`) |
| `research` | Étudier une source ou une API sur sa documentation officielle, avant `ajouter-une-source` |
| `implement` | Coder ce qui a été discuté, en `tdd`, puis relecture et commit sur la branche courante (`/implement`) |
| `diagnosing-bugs` | Bug difficile, régression, lenteur : boucle de reproduction avant toute hypothèse |
| `tdd` | Développement guidé par les tests (paiement, droits d'accès, quotas) |
| `codebase-design` | Vocabulaire et principes pour découper un module |
| `improve-codebase-architecture` | Revue d'architecture à la demande (`/improve-codebase-architecture`) |
| `domain-modeling`, `grilling` | Glossaire, ADR et questions de conception, appelés par les précédentes |
| `retro` | Après une session difficile : améliorer l'environnement de l'agent (`/retro`) |
| `writing-for-agents` | Rédiger ou modifier une skill, `CLAUDE.md` ; appelée par `retro` |
| `wizard` | Script guidé pour une procédure que seul l'humain peut faire (tableaux de bord, clés) |

Les skills génériques viennent de [mattpocock/skills](https://github.com/mattpocock/skills)
(licence MIT), commit `49dd158d1076134a641b33efb035946536778336`, sans les fichiers
`agents/` propres à Codex. Le plugin `mattpocock-skills` est désactivé pour ce dépôt
(`.claude/settings.json`) afin de ne pas charger chaque skill en double. Elles sont rédigées
en anglais : répondre quand même en français. Pour les mettre à jour, recopier les dossiers
depuis un commit précis et relire le diff avant de commiter. Correspondances avec ce dépôt :

- `/code-review` est celui de Claude Code, pas celui de mattpocock/skills.
- `GLOSSARY.md` (racine) fixe le vocabulaire du produit ; `docs/adr/` est créé à la première
  décision à consigner ; les notes de `research` vont dans `docs/recherches/`.
- Les « coding standards » relus en revue dont parle `retro` sont `.claude/rules/`, appliqués
  par `gardien-du-projet` ; il n'y a pas de `CODING_STANDARDS.md`.

## Agents du projet (`.claude/agents/`)

| Agent | Quand |
|---|---|
| `verificateur` | Lancer les contrôles (lint, typage, tests, build) sans charger leur sortie dans le contexte ; à préférer aux commandes directes, notamment pendant `implement` et `tdd` |
| `gardien-du-projet` | Après une implémentation, avant un commit : relit le diff au regard de ce fichier et de `.claude/rules/`, en plus de `/code-review` |

## MCP du projet (`.mcp.json`)

`datagouv` (serveur officiel de data.gouv.fr, lecture seule) : chercher un jeu de données ou une
API publique, vérifier sa licence, sa fraîcheur et ses fichiers avant `research` ou
`ajouter-une-source`, ou repérer un nouveau millésime. Expérimental : une information qui
engage le rapport se confirme sur la page de la source.

## Plugins du projet (`.claude/settings.json`)

- `pyright-lsp` : diagnostics et navigation Python (configuration : `pyrightconfig.json`).
  mypy strict avec le plugin pydantic fait foi : un diagnostic pyright qu'il ne relève pas
  (conversion pydantic, `SecretStr` construit depuis une chaîne…) ne se corrige pas.
- `playwright` : piloter un navigateur pour voir une page après un changement de frontend,
  sur la pile locale (`http://localhost`) uniquement ; jamais de paiement ni de compte sur le
  site en ligne.
