# Audit Immobilier

SaaS d'audit immobilier et de due diligence : l'utilisateur saisit une adresse, l'application
interroge en parallèle une vingtaine de sources publiques et restitue un tableau de bord
(prix, risques, urbanisme, énergie, quartier) exportable en PDF.

État : **MVP « Feature Complete », non déployé.** Ce document sert de passation entre le
développement et l'exploitation.

## Architecture

```
Navigateur ── Vue 3 (Cloudflare Pages, à venir)
    │  autocomplétion : API Base Adresse Nationale (appel direct)
    │  audit : GET /api/v1/audit/stream (Server-Sent Events)
    ▼
Caddy (80/443, TLS automatique) ── seul service exposé
    ▼
FastAPI (backend/) ── pipeline asynchrone aiohttp, 18 sources en parallèle
    ├── API publiques : BAN, Géorisques, API Carto IGN, DVF, ADEME, Overpass,
    │   Atmo France, ANFR, IGN altimétrie, data.gouv, OpenRouteService (facultatif)
    └── PostgreSQL 17 + PostGIS (image Supabase)
          schéma `immo` : cache des rapports + référentiels ingérés
```

| Dossier | Contenu |
|---|---|
| `backend/app/api` | Routes FastAPI (`/api/v1/audit`, `/api/v1/audit/stream`, `/api/v1/sources`, `/health`) |
| `backend/app/services` | Orchestrateur, règles métier (`insights.py`), un fournisseur par source (`providers/`) |
| `backend/app/repositories` | Accès PostgreSQL (cache, référentiels, ingestion) |
| `backend/app/ingestion` | Chargement des référentiels statiques (CLI) |
| `frontend/` | Application Vue 3 + Vite + TypeScript + Tailwind |
| `infra/` | Caddyfile de développement, scripts SQL d'initialisation, sources des cartes de bruit |
| `deploy/` | Fichiers de mise en production (pare-feu, Caddyfile HTTPS) |
| `scripts/` | Génération du `.env`, analyse SonarQube, ingestion du bruit |

Principes à connaître avant d'intervenir :

- **Dégradation gracieuse.** Chaque source a un délai de 9 s et son coupe-circuit. Une source en
  échec ne bloque jamais le rapport : il sort marqué `is_partial`, avec la liste
  `failed_sources`. Overpass est interrogé sur trois serveurs successifs.
- **Cache.** Un rapport complet est conservé 7 jours, un rapport partiel 15 minutes. Changer le
  format du rapport impose d'incrémenter `REPORT_VERSION`.
- **Sécurité des données.** Les tables vivent dans le schéma `immo`, non exposé par PostgREST,
  avec RLS activée. Le backend se connecte avec le rôle `immo_app`, sans droit de DDL.
- **Réseau.** Seul Caddy publie des ports. Postgres (5433), Studio (3100) et SonarQube (9000)
  n'écoutent que sur `127.0.0.1` : on y accède par tunnel SSH.

## Prérequis

| Outil | Version utilisée | Usage |
|---|---|---|
| Docker + Docker Compose | 29 / v5 | Toute la stack serveur |
| Node.js | 22 | Frontend |
| uv | 0.11 | Backend hors conteneur, script d'ingestion du bruit |
| openssl | — | Génération des secrets |

Le serveur visé est un VPS Ubuntu 24.04. Prévoir environ 2 Go de disque pour la base une fois
les référentiels chargés.

## Démarrage en développement

```bash
./scripts/generate-env.sh          # crée .env avec des secrets aléatoires (une seule fois)
docker compose up -d --build       # base, auth, API, proxy : http://localhost
docker compose run --rm backend python -m app.ingestion all   # référentiels, ~30 min
uv run scripts/ingest_bruit_lden.py                           # cartes de bruit

cd frontend
cp .env.example .env
npm install
npm run dev                        # http://localhost:5173
```

## Variables d'environnement

Le modèle est `.env.example` ; `./scripts/generate-env.sh` le copie en `.env` et remplit les
secrets. Le fichier `.env` n'est jamais versionné.

| Variable | Rôle | Développement | Production |
|---|---|---|---|
| `APP_ENV` | `production` masque la documentation de l'API | `production` | `production` |
| `SITE_ADDRESS` | Adresse servie par Caddy | `:80` | `api.mondomaine.fr` |
| `PUBLIC_URL` | URL publique de l'API | `http://localhost` | `https://api.mondomaine.fr` |
| `SITE_URL` | URL du frontend (redirections d'authentification) | `http://localhost:5173` | URL Cloudflare Pages |
| `CORS_ALLOWED_ORIGINS` | Origines autorisées à appeler l'API, séparées par des virgules | `http://localhost:5173` | URL Cloudflare Pages |
| `CADDYFILE` | Configuration de Caddy montée dans le conteneur | `./infra/caddy/Caddyfile` | `./deploy/Caddyfile` |
| `ACME_EMAIL` | Contact Let's Encrypt | vide | adresse de l'exploitant |
| `HTTP_PORT`, `HTTPS_PORT` | Ports publiés par Caddy | `80`, `443` | `80`, `443` |
| `DATA_DIR` | Répertoire des données Postgres | `./data` | `/srv/immo` |
| `DB_HOST_PORT` | Port Postgres sur `127.0.0.1` | `5433` | `5433` |
| `POSTGRES_PASSWORD`, `IMMO_APP_DB_PASSWORD`, `JWT_SECRET`, `ANON_KEY`, `SERVICE_ROLE_KEY`, `PG_META_CRYPTO_KEY`, `SONAR_DB_PASSWORD` | Secrets | générés | générés sur le serveur, jamais copiés depuis le poste de développement |
| `ORS_API_KEY` | Clé OpenRouteService : temps de marche sur itinéraire piéton. Vide = estimation à vol d'oiseau × 1,3 | facultatif | facultatif |
| `ENABLE_EMAIL_AUTOCONFIRM`, `SMTP_*` | Confirmation des comptes par e-mail | autoconfirmation | à configurer avant d'ouvrir l'inscription |
| `SONAR_ADMIN_PASSWORD`, `SONAR_TOKEN` | Écrits par `scripts/sonar-setup.sh` | — | — |

Réglages du backend, facultatifs (valeurs par défaut dans `backend/app/core/config.py`) :
`HTTP_TIMEOUT_S` (9), `PROVIDER_DEADLINE_S` (20), `REPORT_VERSION` (5), `CACHE_TTL_HOURS` (168),
`CACHE_PARTIAL_TTL_MINUTES` (15), `RATE_LIMIT_REQUESTS` (30 par minute et par IP).

Frontend (`frontend/.env`) : `VITE_API_URL`, l'URL publique de l'API.

## Données ingérées

| Jeu | Commande | Fréquence conseillée |
|---|---|---|
| Délinquance (SSMSI), taxe foncière (DGFiP), IPS des établissements, logements par IRIS (INSEE), fibre (ARCEP), permis de construire (SITADEL) | `docker compose run --rm backend python -m app.ingestion all` | Trimestrielle ; mensuelle pour `sitadel` |
| Cartes de bruit stratégiques (Lden) | `uv run scripts/ingest_bruit_lden.py` | Mensuelle |

L'ingestion est idempotente et vide le cache des rapports à la fin. Un jeu ou un département peut
être rechargé seul : `python -m app.ingestion sitadel --departements 49,75`.

### Tâche planifiée du bruit Lden

Le script est autonome (dépendances déclarées en tête de fichier, résolues par `uv`) et lit la
connexion dans le `.env` du projet. Les territoires couverts sont listés dans
`infra/bruit/sources.json` ; il n'existe pas de flux national, chaque département s'ajoute à la
main.

```cron
# crontab -e, sur le VPS : le 2 de chaque mois à 4 h
0 4 2 * * cd /opt/project-immobilier && /usr/local/bin/uv run scripts/ingest_bruit_lden.py >> /var/log/immo-bruit.log 2>&1
```

Options : `--metropole angers`, `--source ddt49-route`. Le script sort en erreur (code 1) si une
source échoue, sans effacer les données déjà chargées.

## Tests et qualité

```bash
cd backend && uv run pytest && uv run mypy app tests && uv run ruff check app tests
cd frontend && npm run test && npm run typecheck && npm run lint && npm run build

docker compose --profile quality up -d   # SonarQube, http://localhost:9000
./scripts/sonar-setup.sh                 # une seule fois par instance
./scripts/sonar-scan.sh                  # échoue si le Quality Gate est rouge
```

En intégration continue, `.github/workflows/sonar.yml` rejoue ces tests puis lance l'analyse à
chaque push ou pull request sur `main`. Il attend les secrets `SONAR_TOKEN` et `SONAR_HOST_URL`,
et pour SonarQube Cloud les variables `SONAR_ORGANIZATION` et `SONAR_PROJECT_KEY`.

Seuils tenus : aucun bug, aucune vulnérabilité, aucun Security Hotspot ouvert, duplication
inférieure à 5 %, complexité par fonction inférieure à 15, typage strict des deux côtés.

## Mise en production (préparée, non exécutée)

### Backend sur le VPS

1. Copier le dépôt dans `/opt/project-immobilier` et créer `/srv/immo`.
2. `./scripts/generate-env.sh`, puis renseigner dans `.env` les valeurs de la colonne
   « Production » ci-dessus.
3. `sudo ./deploy/setup_ufw.sh` (un `--dry-run` affiche les règles sans les appliquer).
4. `docker compose up -d --build`, puis les deux ingestions.
5. Installer la tâche planifiée du bruit.

`deploy/setup_ufw.sh` refuse tout le trafic entrant sauf SSH, HTTP et HTTPS. Docker contourne
UFW pour les ports qu'il publie : ne jamais publier un port interne sans le préfixe
`127.0.0.1:` dans `docker-compose.yml`.

`deploy/Caddyfile` n'expose que l'API FastAPI en HTTPS. Les routes Supabase (`/auth/v1`,
`/rest/v1`) y sont commentées : elles seront à rouvrir avec la connexion utilisateur.

### Frontend sur Cloudflare Pages

| Réglage | Valeur |
|---|---|
| Répertoire racine | `frontend` |
| Commande de build | `npm run build` |
| Dossier de sortie | `dist` |
| Variable | `VITE_API_URL` = URL publique de l'API |

`frontend/public/_redirects` renvoie toute URL vers `index.html`. Dans
`frontend/public/_headers`, remplacer `__API_ORIGIN__` par l'URL de l'API : sans cela, la
politique de sécurité du contenu bloquera les appels.

## Limites connues

- **Connexion utilisateur absente.** L'audit est public, limité en débit. Supabase Auth tourne
  mais le frontend n'a pas d'écran de connexion.
- **Limitation de débit en mémoire** : valable pour un seul processus backend.
- **Transports et commerces** : dépend des serveurs publics Overpass, souvent saturés.
- **Bruit** : Maine-et-Loire (route et fer) et Loire-Atlantique (fer) seulement.
- **Encadrement des loyers** : liste codée en dur d'après service-public.gouv.fr (vérifiée le
  1er août 2026), dans `backend/app/services/providers/rental_rules.py` ; à relire à chaque
  nouveau décret.
- **Charges de copropriété** : moyennes de 2018, proposées comme valeur de départ modifiable.
- **Sauvegardes** : aucune sauvegarde de la base n'est planifiée.
- **Licences à respecter** : indice ATMO (ODbL, attribution Atmo France et association
  régionale), OpenStreetMap (ODbL), données publiques sous Licence Ouverte.
