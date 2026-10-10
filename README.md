# Audit Immobilier

SaaS d'audit immobilier et de due diligence : l'utilisateur saisit une adresse, l'application
interroge en parallèle une vingtaine de sources publiques et restitue un tableau de bord
(prix, risques, urbanisme, énergie, quartier) exportable en PDF.

État : **en production** sur `https://audit-immobilier.fr` (Cloudflare Pages) et
`https://api.audit-immobilier.fr` (VPS). Les paiements Stripe y tournent encore en mode test.
Ce document sert de passation entre le développement et l'exploitation.

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
  `failed_sources`.
- **Cache par source.** Un rapport reste en base sept jours, mais sa fraîcheur se juge source
  par source : une source en échec ou incomplète est réinterrogée seule après 15 minutes,
  l'indice de l'air après 12 heures ; les autres sont reprises du cache. Une lecture qui
  échoue vite sur une erreur passagère (502, connexion coupée) est rejouée une fois.
- **Modèle « teaser ».** Sans achat de l'adresse, l'API renvoie le rapport avec les valeurs
  réservées remplacées par `"***LOCKED***"` (`backend/app/services/teaser.py`, liste blanche
  par source : tout nouveau champ est masqué par défaut). Le masquage est fait côté serveur ;
  le flou du frontend n'est qu'un habillage. L'accès complet exige un jeton de session Supabase
  valide et une ligne dans `immo.audit_entitlements` pour cette adresse. Cette table sera
  alimentée par le paiement (Stripe, à venir) ; d'ici là, un droit s'ouvre à la main en SQL.
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
| `GOOGLE_ENABLED`, `GOOGLE_CLIENT_ID`, `GOOGLE_SECRET` | Connexion « Continuer avec Google » ; URI de redirection à déclarer chez Google : `<PUBLIC_URL>/auth/v1/callback` | désactivé | identifiants Google Cloud |
| `ADDITIONAL_REDIRECT_URLS` | Adresses de retour autorisées après connexion | `http://localhost:5173/**` | `https://<frontend>/**` |
| `ORS_API_KEY` | Clé OpenRouteService : temps de marche sur itinéraire piéton. Vide = estimation à vol d'oiseau × 1,3 | facultatif | facultatif |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | Clés Stripe (voir « Paiement Stripe »). Vides = paiement fermé (503) | facultatif | requis |
| `STRIPE_PRO_TAX_RATE_ID` | Taux de TVA Stripe (`txr_...`) ajouté au prix HT de l'offre Pro | facultatif | recommandé |
| `ENABLE_EMAIL_AUTOCONFIRM`, `SMTP_*` | Confirmation des comptes par e-mail | autoconfirmation | à configurer avant d'ouvrir l'inscription |
| `SONAR_ADMIN_PASSWORD`, `SONAR_TOKEN` | Écrits par `scripts/sonar-setup.sh` | — | — |

Réglages du backend, facultatifs (valeurs par défaut dans `backend/app/core/config.py`) :
`HTTP_TIMEOUT_S` (9), `PROVIDER_DEADLINE_S` (20), `REPORT_VERSION` (5), `CACHE_TTL_HOURS` (168),
`CACHE_PARTIAL_TTL_MINUTES` (15), `RATE_LIMIT_REQUESTS` (30 par minute et par IP).

Frontend (`frontend/.env`) : `VITE_API_URL`, l'URL publique de l'API, et
`VITE_SUPABASE_ANON_KEY`, la clé publique `ANON_KEY` du `.env` racine (nécessaire à la création
de compte ; ce n'est pas un secret).

## Données ingérées

| Jeu | Commande | Fréquence conseillée |
|---|---|---|
| Délinquance (SSMSI), taxe foncière (DGFiP), IPS des établissements, logements par IRIS (INSEE), fibre (ARCEP), carte des loyers (ANIL), zones tendues (zonage TLV), carte scolaire des collèges publics, permis de construire (SITADEL) | `docker compose run --rm backend python -m app.ingestion all` | Trimestrielle ; mensuelle pour `sitadel` |
| Cartes de bruit stratégiques (Lden) | `uv run scripts/ingest_bruit_lden.py` | Mensuelle |

L'ingestion est idempotente et vide le cache des rapports à la fin. Un jeu ou un département peut
être rechargé seul : `python -m app.ingestion sitadel --departements 49,75`.

### Points d'intérêt OpenStreetMap

Le bloc « Transports et commerces à pied » lit la table `immo.geo_osm_poi`, et non plus les
serveurs publics Overpass (saturés : une requête sur deux y échouait). Overpass ne sert que de
secours pour un secteur non ingéré.

```bash
uv run scripts/ingest_osm_poi.py                           # France entière (~5 Go téléchargés)
uv run scripts/ingest_osm_poi.py --region pays-de-la-loire # une région Geofabrik
# crontab -e, sur le VPS : le 3 de chaque mois à 4 h
0 4 3 * * cd /opt/project-immobilier && uv run scripts/ingest_osm_poi.py >> /var/log/immo-osm.log 2>&1
```

Données © les contributeurs d'OpenStreetMap (ODbL), extraits fournis par Geofabrik.

### Sources interrogées en direct pour le bâtiment et les risques complémentaires

| Donnée | Source | Limite connue |
| --- | --- | --- |
| Bâtiment à l'adresse, copropriété immatriculée | API ouverte de la BDNB (CSTB), par identifiant BAN | 120 requêtes par minute et par IP, trois par audit |
| Plans de prévention, territoires à risque d'inondation | Géorisques (`gaspar/pprn`, `gaspar/tri`) | plans listés à l'échelle de la commune |
| Anciens sites industriels, cavités, mouvements de terrain | Géorisques (`ssp/casias`, `cavites`, `mvt`), rayon de 500 m | inventaires non exhaustifs |
| Servitudes d'utilité publique, prescriptions | API Carto, Géoportail de l'urbanisme | selon les documents versés par la commune |
| Zonage ABC | API tabulaire de data.gouv.fr | identifiants de ressource millésimés dans la configuration |
| Loyers par typologie | table `ref_loyers` (toutes les communes, Paris/Lyon/Marseille par arrondissement) ; API tabulaire de data.gouv.fr en repli | `python -m app.ingestion loyers`. Nouvelle édition : mettre à jour `LOYERS_MILLESIME` et les quatre `LOYERS_*_RESOURCE_ID`, puis relancer (les lignes de l'ancien millésime sont retirées) |

### Tâche planifiée du bruit Lden

Le script est autonome (dépendances déclarées en tête de fichier, résolues par `uv`) et lit la
connexion dans le `.env` du projet. Il n'existe pas de flux national : chaque direction
départementale publie ses cartes sur Géo-IDE. `scripts/discover_bruit_sources.py` recense ces
flux à partir de data.gouv.fr et écrit `infra/bruit/sources.json` (couches de type A en Lden,
édition courante de chaque département) ; le relancer quand de nouvelles cartes paraissent.

```cron
# crontab -e, sur le VPS : le 2 de chaque mois à 4 h
0 4 2 * * cd /opt/project-immobilier && /usr/local/bin/uv run scripts/ingest_bruit_lden.py >> /var/log/immo-bruit.log 2>&1
```

Options : `--departement 49`, `--source d49-infra_r_a_ld_s_049`, `--parallele 4`. Une source en
échec garde ses données déjà chargées ; le script sort en erreur (code 1) dès qu'une source
échoue. Un passage complet retire les zones des sources absentes du fichier.

### Tests d'intégration SQL

Les tests unitaires simulent le dépôt. `backend/tests/test_integration_sql.py` exécute les
requêtes géographiques et les agrégats sur une vraie base (bruit le long d'une voie, préfixes
d'arrondissements, distance au contour d'un parc). Ils sont ignorés sans base, donc en CI :

```bash
cd backend && IMMO_TEST_DATABASE_URL=postgresql://immo_app:<mot de passe>@127.0.0.1:5433/postgres \
    uv run pytest tests/test_integration_sql.py
```

Chaque test insère ses propres lignes sous des codes inexistants et les retire en sortant.

### Test de fumée

Les tests unitaires simulent toutes les API. Pour détecter une source arrêtée, déplacée ou
dont la réponse a changé de forme, un test interroge les vraies sources sur une adresse et
une rue de référence, sans passer par le cache :

```bash
docker compose exec -T backend python -m app.smoke   # code de retour 1 en cas d'anomalie
# crontab -e, sur le VPS : chaque nuit à 3 h
0 3 * * * cd /opt/project-immobilier && docker compose exec -T backend python -m app.smoke >> /var/log/immo-smoke.log 2>&1
```

## Espace client et marque blanche

- `/compte` : offre en cours, adresses débloquées (chacune se rouvre d'un clic) et, pour les
  abonnés Pro, la marque blanche des rapports.
- Marque blanche : le nom et le logo de l'abonné figurent en tête du PDF, et le pied de page
  indique « Rapport remis par… ». Les sources restent citées : leurs licences l'exigent.
- Le logo est contrôlé par le serveur d'après son contenu réel : PNG ou JPEG de 200 Ko au
  plus, jamais de SVG. Il n'est servi qu'aux abonnés actifs.

## Compte client : mot de passe, suppression, remboursement

- **Mot de passe oublié** : lien dans la fenêtre de connexion, e-mail à la charte du site, puis
  page `/mot-de-passe` pour en choisir un nouveau.
- **Suppression du compte** par son titulaire depuis `/compte` : l'abonnement en cours est
  arrêté chez Stripe, puis le compte est supprimé par l'interface d'administration du service
  d'authentification (clé de service, réseau interne). Droits, crédits, marque blanche et
  historique partent avec lui.
- **Remboursement** : un remboursement intégral dans Stripe (`charge.refunded`) retire l'adresse
  débloquée par l'achat et les crédits de pack encore disponibles. Un remboursement partiel ne
  retire rien. Les paiements antérieurs à cette version ne portent pas les informations
  nécessaires : leur remboursement n'a pas d'effet automatique.
- **Historique** : chaque rapport complet servi est noté, pour qu'un abonné retrouve les
  adresses qu'il a étudiées.

## E-mails

Deux familles de messages, à la charte du site (`backend/app/services/emails.py`) :

- **authentification** (confirmation d'adresse, mot de passe oublié) : envoyés par le service
  d'authentification, qui lit ses gabarits auprès du backend sur le réseau interne ;
- **reçu de paiement** : envoyé par le backend quand Stripe signale une facture payée
  (`invoice.paid`), avec le récapitulatif et le lien vers la facture PDF émise par Stripe.

Les deux utilisent le même serveur SMTP (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`,
`SMTP_ADMIN_EMAIL` pour l'expéditeur). Sans serveur configuré, aucun reçu n'est envoyé ; pour
exiger la confirmation des comptes, passer `ENABLE_EMAIL_AUTOCONFIRM=false`. Le webhook Stripe
doit aussi recevoir l'évènement `invoice.paid`.

## Sauvegardes et tâches planifiées

```bash
sudo ./deploy/install-cron.sh              # installe toutes les tâches (--dry-run pour voir)
sudo ./deploy/backup.sh                    # sauvegarde immédiate dans /srv/immo-backups
sudo ./deploy/restore.sh <fichier.dump>    # remplace comptes et droits par ceux du fichier
./scripts/deploy-backend.sh root@<serveur> # met à jour le backend depuis ce poste
```

Chaque tâche planifiée passe par `deploy/run-task.sh` : sa sortie est journalisée dans
`/var/log/immo-*.log` et un échec envoie un e-mail à `ALERT_EMAIL` (dernières lignes du journal).

La sauvegarde quotidienne contient ce qui ne se reconstruit pas : comptes, droits d'accès,
crédits, abonnements, marque blanche. Les référentiels publics en sont exclus (ils se
rechargent par ingestion). Elle est relue avant d'être gardée, et 14 jours sont conservés.
**Copie hors site** : si `R2_BUCKET`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID` et
`R2_SECRET_ACCESS_KEY` sont renseignés dans le `.env` du serveur, chaque sauvegarde est aussi
envoyée sur Cloudflare R2, puis sa taille est relue sur le stockage. Un envoi en échec fait
sortir le script en erreur, la copie locale étant conservée. La durée de conservation sur R2
se règle par une règle de cycle de vie du bucket. Pour repartir d'un serveur neuf :
`./deploy/backup-fetch.sh immo-AAAA-MM-JJ-HHMM.dump`, puis `./deploy/restore.sh`.

## Référencement

Une application monopage ne livre aux robots qu'une coquille vide. Le site expose donc :

- **des balises par page** (titre, description, URL canonique, Open Graph), mises à jour à
  chaque navigation ; le rapport d'une adresse est marqué `noindex`, car il contient des
  ventes DVF dont les conditions de réutilisation excluent l'indexation ;
- **une fiche par commune** (`/commune/angers-49007`) : taxe foncière, cambriolages, écoles,
  logement et fibre, comparés au département et à la France. Ces chiffres communaux sont
  publics et gratuits ; l'audit d'une adresse reste le produit payant ;
- **des pages statiques** : à la construction, `scripts/seo.ts` écrit chaque fiche en HTML
  dans `dist/commune/<slug>.html` (servie sans barre finale, comme l'annoncent le plan du
  site et la balise canonique), ainsi que `sitemap.xml`, `robots.txt` et `communes.json` ;
- **un vrai code 404** : chaque page de l'application a son fichier (`tarifs.html`…), et
  `404.html` répond aux adresses inconnues. Les communes sans fiche statique sont rendues
  par l'application grâce à la fonction `functions/commune/[slug].js`, limitée à
  `/commune/*` par `_routes.json`. `npx wrangler pages dev dist` reproduit ce comportement
  en local.

```bash
# Régénérer les fiches (après une ingestion), puis construire le site
docker compose exec -T backend python -m app.seo --limit 1000 > frontend/seo/communes.json
cd frontend && VITE_SITE_URL=https://mondomaine.fr npm run build
```

`frontend/seo/communes.json` est versionné pour que la construction sur Cloudflare Pages
n'ait pas besoin de la base. Sans `VITE_SITE_URL`, le plan du site n'est pas produit (il exige
des adresses absolues). Le fond de carte est le Plan IGN de la Géoplateforme, service public
ouvert sans clé.

## Paiement Stripe et connexion Google

### Stripe

Le navigateur n'ouvre jamais un droit : il demande une session de paiement
(`POST /api/v1/checkout`, prix fixé côté serveur), puis Stripe confirme l'achat au backend
par un évènement signé (`POST /api/v1/stripe/webhook`). Seul cet évènement crée le droit sur
l'adresse, les crédits du pack ou l'abonnement. Sans clés, ces routes répondent 503.

| Offre | Montant débité | Effet |
| --- | --- | --- |
| `unit` | 4,99 € | débloque l'adresse |
| `pack` | 24,99 € | débloque l'adresse + 9 crédits (10 crédits sans adresse) |
| `pro` | 49,00 € / mois | toutes les adresses tant que l'abonnement est actif |

Mise en route en local (mode test, aucun débit réel) :

1. Dans le tableau de bord Stripe, mode **Test** : *Developers > API keys*, copier la clé
   secrète `sk_test_...` dans `STRIPE_SECRET_KEY` (fichier `.env`).
2. Installer la [CLI Stripe](https://docs.stripe.com/stripe-cli), puis :
   ```bash
   stripe login
   stripe listen --all-snapshot --forward-to localhost/api/v1/stripe/webhook
   ```
   La commande affiche un secret `whsec_...` : le copier dans `STRIPE_WEBHOOK_SECRET`.
   Ne pas utiliser `--all-thin` : ce mode ne transmet pas `checkout.session.completed`.
3. `docker compose up -d backend`, puis payer avec la carte de test `4242 4242 4242 4242`
   (date future, CVC quelconque).

En production : créer le webhook dans *Developers > Webhooks* vers
`<PUBLIC_URL>/api/v1/stripe/webhook` avec les évènements `checkout.session.completed`,
`checkout.session.async_payment_succeeded`, `customer.subscription.updated` et
`customer.subscription.deleted`, et activer le portail client (*Settings > Billing > Customer
portal*) qui sert à la résiliation de l'offre Pro.

### Google

1. [Google Cloud Console](https://console.cloud.google.com/) : créer un projet, configurer
   l'écran de consentement OAuth (type *Externe*, champs d'application `email` et `profile`).
2. *Identifiants > Créer des identifiants > ID client OAuth*, type *Application Web* :
   - origine JavaScript autorisée : l'adresse du frontend (`http://localhost:5173` en local) ;
   - URI de redirection autorisé : `<PUBLIC_URL>/auth/v1/callback`
     (`http://localhost/auth/v1/callback` en local).
3. Dans `.env` : `GOOGLE_ENABLED=true`, `GOOGLE_CLIENT_ID`, `GOOGLE_SECRET`, puis
   `docker compose up -d auth`.

## Tests et qualité

```bash
cd backend && uv run pytest && uv run mypy app tests && uv run ruff check app tests
cd frontend && npm run test && npm run typecheck && npm run lint && npm run build

docker compose --profile quality up -d   # SonarQube, http://localhost:9000
./scripts/sonar-setup.sh                 # une seule fois par instance
./scripts/sonar-scan.sh                  # échoue si le Quality Gate est rouge
```

En intégration continue, `.github/workflows/ci.yml` rejoue le style, le typage, les tests et le
build à chaque push ou pull request sur `main`, sans aucun secret à configurer. L'analyse
SonarQube reste locale et gratuite (édition Community, commandes ci-dessus) : SonarQube Cloud
n'est pas utilisé.

Seuils tenus : aucun bug, aucune vulnérabilité, aucun Security Hotspot ouvert, duplication
inférieure à 5 %, complexité par fonction inférieure à 15, typage strict des deux côtés.

## Mise en production

### Backend sur le VPS

1. Copier le dépôt dans `/opt/project-immobilier` et créer `/srv/immo`.
2. `./scripts/generate-env.sh`, puis renseigner dans `.env` les valeurs de la colonne
   « Production » ci-dessus.
3. `sudo ./deploy/setup_ufw.sh` (un `--dry-run` affiche les règles sans les appliquer).
4. `docker compose up -d --build`, puis les ingestions.
5. `./deploy/install-cron.sh` installe les tâches planifiées (sauvegardes, ingestions,
   test de fumée).

Les livraisons suivantes passent par `./scripts/deploy-backend.sh root@<serveur>` : le
script envoie le dernier commit, reconstruit le backend et rejoue le schéma. Le frontend,
lui, est publié par Cloudflare Pages à chaque push sur `main` : pousser puis déployer le
backend dans la foulée, pour que les deux restent sur la même version.

`deploy/setup_ufw.sh` refuse tout le trafic entrant sauf SSH, HTTP et HTTPS. Docker contourne
UFW pour les ports qu'il publie : ne jamais publier un port interne sans le préfixe
`127.0.0.1:` dans `docker-compose.yml`.

`deploy/Caddyfile` expose en HTTPS l'API FastAPI et l'authentification Supabase (`/auth/v1`).
PostgREST (`/rest/v1`) reste interne.

### Frontend sur Cloudflare Pages

| Réglage | Valeur |
|---|---|
| Répertoire racine | `frontend` |
| Commande de build | `npm run build` |
| Dossier de sortie | `dist` |
| Variable | `VITE_API_URL` = URL publique de l'API |

| Variable | `VITE_SITE_URL` = adresse publique du site (plan du site, balises canoniques) |

Dans `frontend/public/_headers`, le repère `__API_ORIGIN__` est remplacé à la construction
par l'origine de `VITE_API_URL` : sans cette variable, la politique de sécurité du contenu
bloque les appels à l'API.

## Limites connues

- **Paiement en mode test** : la production utilise les clés de test Stripe ; aucun
  encaissement réel tant que les clés et le webhook de production ne sont pas configurés.
- **Mentions légales incomplètes** : l'identité de l'éditeur reste à renseigner dans
  `frontend/src/lib/legal.ts` ; d'ici là, les pages légales ne sont pas indexées.
- **Surveillance** : test de fumée et alertes tournent sur le serveur lui-même ; rien ne
  prévient s'il tombe entièrement.
- **Limitation de débit en mémoire** : valable pour un seul processus backend.
- **Transports et commerces** : données OpenStreetMap figées à la date de la dernière ingestion
  (tâche mensuelle).
- **Bruit** : cartes des grandes infrastructures routières et ferroviaires de 65 départements
  (dont Paris, la petite couronne et le Rhône), soit environ 708 000 zones. Les autres
  départements n'ont pas de flux publié sur Géo-IDE, ou un flux illisible à l'ingestion
  (sources marquées `"actif": false` dans `infra/bruit/sources.json`, avec le motif) :
  notamment les Bouches-du-Rhône, la Gironde, le Nord, la Haute-Garonne et le Bas-Rhin. Les
  cartes d'agglomération (voirie communale) et le bruit des aéroports ne sont pas chargés.
- **Encadrement des loyers** : liste codée en dur d'après service-public.gouv.fr (vérifiée le
  1er août 2026), dans `backend/app/services/providers/rental_rules.py` ; à relire à chaque
  nouveau décret.
- **Charges de copropriété** : moyennes de 2018, proposées comme valeur de départ modifiable.
- **Sauvegardes** : quotidiennes, copiées hors site sur Cloudflare R2, mais non chiffrées.
- **Licences à respecter** : indice ATMO (ODbL, attribution Atmo France et association
  régionale), OpenStreetMap (ODbL), données publiques sous Licence Ouverte.
