-- ============================================================================
-- Audit Immobilier — schéma applicatif (étape 2)
--
-- Monté dans le conteneur Postgres (exécuté à la première initialisation,
-- après immo.sql qui crée le rôle immo_app et le schéma immo).
-- Idempotent : peut être rejoué sur une base existante avec
--   docker compose exec -T db psql -U supabase_admin -v ON_ERROR_STOP=1 \
--     -f /docker-entrypoint-initdb.d/init-scripts/99-zzz-init.sql
--
-- Toutes les tables vivent dans le schéma `immo`, non exposé par PostgREST.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Extensions
-- ----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA extensions;
-- postgis_topology impose son propre schéma `topology`.
CREATE EXTENSION IF NOT EXISTS postgis_topology;
-- Planification de la purge du cache.
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Les fonctions PostGIS sont résolues via le schéma `extensions` pendant ce script.
SET search_path = immo, public, extensions;

-- Code commune INSEE : 5 caractères, Corse (2A/2B) et outre-mer (97x/98x) inclus.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'immo' AND t.typname = 'code_insee'
    ) THEN
        CREATE DOMAIN immo.code_insee AS text
            CHECK (VALUE ~ '^(?:[0-9]{2}|2[AB])[0-9]{3}$');
    END IF;
END
$$;

-- ----------------------------------------------------------------------------
-- 2. Cache des rapports d'audit
-- ----------------------------------------------------------------------------
-- Clé composite (geohash, ban_id, report_version) :
--   * geohash        : hash spatial de précision 9 (cellule d'environ 5 m),
--                      calculé par la base à partir de `geom` ;
--   * ban_id         : identifiant BAN du résultat sélectionné (géocode précis),
--                      '' si la recherche vient de coordonnées brutes ; distingue
--                      deux adresses tombant dans la même cellule ;
--   * report_version : version du format du rapport ; l'incrémenter côté backend
--                      invalide tout le cache sans rien supprimer.
CREATE TABLE IF NOT EXISTS immo.api_reports_cache (
    geohash        text        GENERATED ALWAYS AS (extensions.ST_GeoHash(geom, 9)) STORED,
    ban_id         text        NOT NULL DEFAULT '',
    report_version smallint    NOT NULL DEFAULT 1,
    geom           extensions.geometry(Point, 4326) NOT NULL,
    code_insee     immo.code_insee NOT NULL,
    label          text        NOT NULL,
    payload        jsonb       NOT NULL,
    -- true si au moins une source a échoué : le backend applique un TTL court.
    is_partial     boolean     NOT NULL DEFAULT false,
    created_at     timestamptz NOT NULL DEFAULT now(),
    expires_at     timestamptz NOT NULL,
    CONSTRAINT api_reports_cache_pkey PRIMARY KEY (geohash, ban_id, report_version),
    CONSTRAINT api_reports_cache_ttl_check CHECK (expires_at > created_at),
    CONSTRAINT api_reports_cache_payload_check CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT api_reports_cache_label_check CHECK (char_length(label) BETWEEN 1 AND 300),
    CONSTRAINT api_reports_cache_ban_id_check CHECK (char_length(ban_id) <= 64)
);

-- Purge des entrées expirées (balayage ordonné sur expires_at).
CREATE INDEX IF NOT EXISTS api_reports_cache_expires_at_idx
    ON immo.api_reports_cache (expires_at);

CREATE OR REPLACE FUNCTION immo.purge_expired_reports()
RETURNS bigint
LANGUAGE sql
SET search_path = ''
AS $$
    WITH deleted AS (
        DELETE FROM immo.api_reports_cache WHERE expires_at <= now() RETURNING 1
    )
    SELECT count(*) FROM deleted;
$$;

-- ----------------------------------------------------------------------------
-- 3. Référentiels statiques (open data)
-- ----------------------------------------------------------------------------

-- SSMSI — délinquance enregistrée par commune, format long
-- (une ligne par commune x indicateur x année).
CREATE TABLE IF NOT EXISTS immo.insee_ssmsi (
    code_insee       immo.code_insee NOT NULL,
    indicateur       text        NOT NULL,
    annee            smallint    NOT NULL,
    unite_de_compte  text        NOT NULL,
    -- false : valeur sous le seuil de diffusion (secret statistique), nombre/taux NULL.
    est_diffuse      boolean     NOT NULL,
    nombre           integer,
    taux_pour_mille  numeric(10, 4),
    population       integer,
    imported_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT insee_ssmsi_pkey PRIMARY KEY (code_insee, indicateur, annee),
    CONSTRAINT insee_ssmsi_annee_check CHECK (annee BETWEEN 2000 AND 2100),
    CONSTRAINT insee_ssmsi_nombre_check CHECK (nombre IS NULL OR nombre >= 0),
    CONSTRAINT insee_ssmsi_taux_check CHECK (taux_pour_mille IS NULL OR taux_pour_mille >= 0)
);

-- DGFiP (REI) — taux de taxe foncière sur les propriétés bâties par commune.
CREATE TABLE IF NOT EXISTS immo.insee_dgfip (
    code_insee        immo.code_insee NOT NULL,
    annee             smallint    NOT NULL,
    libelle_commune   text        NOT NULL,
    taux_tfb_commune  numeric(6, 2) NOT NULL,
    taux_tfb_epci     numeric(6, 2) NOT NULL DEFAULT 0,
    taux_teom         numeric(6, 2),
    -- Taux global officiel : commune + intercommunalité + taxes annexes (GEMAPI, TSE), hors TEOM.
    taux_tfb_total    numeric(7, 2) NOT NULL,
    imported_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT insee_dgfip_pkey PRIMARY KEY (code_insee, annee),
    CONSTRAINT insee_dgfip_annee_check CHECK (annee BETWEEN 2000 AND 2100),
    CONSTRAINT insee_dgfip_taux_check CHECK (
        taux_tfb_commune >= 0 AND taux_tfb_epci >= 0 AND taux_tfb_total >= 0
        AND (taux_teom IS NULL OR taux_teom >= 0)
    )
);

-- Éducation nationale — établissements géolocalisés avec indice de position sociale.
CREATE TABLE IF NOT EXISTS immo.geo_ips_ecoles (
    uai                 text        NOT NULL,
    rentree_scolaire    smallint    NOT NULL,
    nom                 text        NOT NULL,
    type_etablissement  text        NOT NULL,
    secteur             text        NOT NULL,
    code_insee          immo.code_insee NOT NULL,
    ips                 numeric(5, 1) NOT NULL,
    ecart_type_ips      numeric(5, 1),
    geom                extensions.geometry(Point, 4326) NOT NULL,
    imported_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT geo_ips_ecoles_pkey PRIMARY KEY (uai, rentree_scolaire),
    CONSTRAINT geo_ips_ecoles_uai_check CHECK (uai ~ '^[0-9]{7}[A-Z]$'),
    CONSTRAINT geo_ips_ecoles_type_check
        CHECK (type_etablissement IN ('ecole', 'college', 'lycee')),
    CONSTRAINT geo_ips_ecoles_secteur_check CHECK (secteur IN ('public', 'prive')),
    CONSTRAINT geo_ips_ecoles_ips_check CHECK (ips BETWEEN 0 AND 250)
);

CREATE INDEX IF NOT EXISTS geo_ips_ecoles_geom_gist
    ON immo.geo_ips_ecoles USING gist (geom);
-- Recherches par rayon en mètres : ST_DWithin(geom::geography, point, rayon).
CREATE INDEX IF NOT EXISTS geo_ips_ecoles_geog_gist
    ON immo.geo_ips_ecoles USING gist ((geom::extensions.geography));
CREATE INDEX IF NOT EXISTS geo_ips_ecoles_code_insee_idx
    ON immo.geo_ips_ecoles (code_insee);
-- Dernière rentrée publiée (max) sans parcourir la table.
CREATE INDEX IF NOT EXISTS geo_ips_ecoles_rentree_idx
    ON immo.geo_ips_ecoles (rentree_scolaire);

-- SITADEL — autorisations d'urbanisme récentes géocodées via la BAN (risque de vis-à-vis).
CREATE TABLE IF NOT EXISTS immo.geo_sitadel (
    num_permis               text        NOT NULL,
    type_autorisation        text        NOT NULL,
    etat                     text        NOT NULL,
    date_autorisation        date        NOT NULL,
    date_ouverture_chantier  date,
    date_achevement          date,
    code_insee               immo.code_insee NOT NULL,
    adresse                  text,
    nature_projet            text,
    destination              text,
    nb_logements             integer,
    nb_niveaux               smallint,
    surface_plancher_m2      numeric(12, 2),
    geom                     extensions.geometry(Point, 4326) NOT NULL,
    -- 'numero' : géocodé à l'adresse ; 'voie' : au milieu de la rue (imprécis pour un vis-à-vis).
    precision_geocodage      text        NOT NULL,
    imported_at              timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT geo_sitadel_pkey PRIMARY KEY (num_permis),
    CONSTRAINT geo_sitadel_precision_check CHECK (precision_geocodage IN ('numero', 'voie')),
    CONSTRAINT geo_sitadel_type_check CHECK (type_autorisation IN ('PC', 'PA', 'DP', 'PD')),
    CONSTRAINT geo_sitadel_etat_check
        CHECK (etat IN ('autorise', 'commence', 'termine', 'annule')),
    CONSTRAINT geo_sitadel_nb_logements_check CHECK (nb_logements IS NULL OR nb_logements >= 0),
    CONSTRAINT geo_sitadel_nb_niveaux_check CHECK (nb_niveaux IS NULL OR nb_niveaux >= 0),
    CONSTRAINT geo_sitadel_surface_check
        CHECK (surface_plancher_m2 IS NULL OR surface_plancher_m2 >= 0)
);

CREATE INDEX IF NOT EXISTS geo_sitadel_geom_gist
    ON immo.geo_sitadel USING gist (geom);
CREATE INDEX IF NOT EXISTS geo_sitadel_geog_gist
    ON immo.geo_sitadel USING gist ((geom::extensions.geography));
CREATE INDEX IF NOT EXISTS geo_sitadel_commune_date_idx
    ON immo.geo_sitadel (code_insee, date_autorisation DESC);

-- INSEE — recensement, logements par IRIS (statut d'occupation, vacance).
CREATE TABLE IF NOT EXISTS immo.insee_iris_logement (
    code_iris               text        NOT NULL,
    annee                   smallint    NOT NULL,
    code_insee              immo.code_insee NOT NULL,
    logements               integer     NOT NULL,
    residences_principales  integer     NOT NULL,
    residences_secondaires  integer     NOT NULL,
    logements_vacants       integer     NOT NULL,
    proprietaires           integer     NOT NULL,
    locataires              integer     NOT NULL,
    locataires_hlm          integer     NOT NULL,
    imported_at             timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT insee_iris_logement_pkey PRIMARY KEY (code_iris),
    CONSTRAINT insee_iris_logement_code_check CHECK (code_iris ~ '^[0-9AB]{9}$'),
    CONSTRAINT insee_iris_logement_counts_check CHECK (
        logements >= 0 AND residences_principales >= 0 AND residences_secondaires >= 0
        AND logements_vacants >= 0 AND proprietaires >= 0 AND locataires >= 0
        AND locataires_hlm >= 0
    )
);

-- ARCEP — éligibilité des locaux aux réseaux fixes, par commune (« Ma connexion internet »).
CREATE TABLE IF NOT EXISTS immo.arcep_connectivite (
    code_insee          immo.code_insee NOT NULL,
    date_donnees        date        NOT NULL,
    nb_locaux           integer     NOT NULL,
    eligibles_fibre     integer     NOT NULL,
    eligibles_cable     integer     NOT NULL,
    eligibles_4g_fixe   integer     NOT NULL,
    imported_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT arcep_connectivite_pkey PRIMARY KEY (code_insee),
    CONSTRAINT arcep_connectivite_counts_check CHECK (
        nb_locaux >= 0 AND eligibles_fibre >= 0 AND eligibles_cable >= 0 AND eligibles_4g_fixe >= 0
    )
);

-- Cartes de bruit stratégiques (indice Lden), ingérées par scripts/ingest_bruit_lden.py
-- depuis les flux WFS Géo-IDE des directions départementales (schéma COVADIS « ZBR »).
CREATE TABLE IF NOT EXISTS immo.geo_bruit_lden (
    id_zone         text        NOT NULL,
    source_id       text        NOT NULL,
    code_dept       text        NOT NULL,
    -- 'route', 'fer', 'air' ou 'industrie'
    infrastructure  text        NOT NULL,
    code_infra      text,
    annee           smallint,
    -- Borne basse de la classe de bruit en dB(A) : 55 signifie « 55 à 60 dB ».
    db_min          smallint    NOT NULL,
    geom            extensions.geometry(MultiPolygon, 4326) NOT NULL,
    imported_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT geo_bruit_lden_pkey PRIMARY KEY (id_zone),
    CONSTRAINT geo_bruit_lden_infra_check
        CHECK (infrastructure IN ('route', 'fer', 'air', 'industrie')),
    CONSTRAINT geo_bruit_lden_db_check CHECK (db_min BETWEEN 30 AND 100)
);

CREATE INDEX IF NOT EXISTS geo_bruit_lden_geom_gist
    ON immo.geo_bruit_lden USING gist (geom);
CREATE INDEX IF NOT EXISTS geo_bruit_lden_source_idx
    ON immo.geo_bruit_lden (source_id);

-- Points d'intérêt OpenStreetMap (transports, commerces, santé, écoles, parcs), ingérés par
-- scripts/ingest_osm_poi.py depuis les extraits Geofabrik : évite de dépendre, à chaque audit,
-- des serveurs publics Overpass.
CREATE TABLE IF NOT EXISTS immo.geo_osm_poi (
    -- 'n' (nœud), 'w' (chemin) ou 'r' (relation)
    osm_type     char(1)     NOT NULL,
    osm_id       bigint      NOT NULL,
    categorie    text        NOT NULL,
    type         text        NOT NULL,
    nom          text,
    -- Extrait d'origine : sert à purger les objets disparus lors d'une réingestion.
    source       text        NOT NULL,
    -- Point pour un nœud ; sommets du contour (MultiPoint) pour un chemin ou une relation, afin
    -- qu'un parc soit « à portée » dès que son bord l'est, et non son centre.
    geom         extensions.geometry(Geometry, 4326) NOT NULL,
    imported_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT geo_osm_poi_pkey PRIMARY KEY (osm_type, osm_id),
    CONSTRAINT geo_osm_poi_type_check CHECK (osm_type IN ('n', 'w', 'r'))
);

CREATE INDEX IF NOT EXISTS geo_osm_poi_geog_gist
    ON immo.geo_osm_poi USING gist ((geom::extensions.geography));
CREATE INDEX IF NOT EXISTS geo_osm_poi_source_idx
    ON immo.geo_osm_poi (source);

-- Carte des loyers (ANIL, ministère chargé du logement) : loyer d'annonce au m², charges
-- comprises, par commune et par type de bien. Paris, Lyon et Marseille y figurent par
-- arrondissement. Ingérée par `python -m app.ingestion loyers`.
CREATE TABLE IF NOT EXISTS immo.ref_loyers (
    code_insee         immo.code_insee NOT NULL,
    -- 'appartement', 't1_t2', 't3_plus' ou 'maison'
    type_bien          text        NOT NULL,
    -- Précision de la source conservée : l'arrondi se fait une seule fois, à l'affichage.
    loyer_m2           numeric(8,4) NOT NULL,
    borne_basse        numeric(8,4),
    borne_haute        numeric(8,4),
    nb_observations    integer,
    -- 'commune' : estimé sur les annonces de la commune ; 'maille' : sur un groupe de communes.
    niveau_prediction  text,
    millesime          smallint    NOT NULL,
    imported_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ref_loyers_pkey PRIMARY KEY (code_insee, type_bien),
    CONSTRAINT ref_loyers_type_check
        CHECK (type_bien IN ('appartement', 't1_t2', 't3_plus', 'maison')),
    CONSTRAINT ref_loyers_loyer_check CHECK (loyer_m2 > 0)
);

-- Zonage de la taxe sur les logements vacants (ministère chargé du logement) : communes en
-- zone tendue. Ingéré par `python -m app.ingestion zone_tendue`.
CREATE TABLE IF NOT EXISTS immo.ref_zone_tendue (
    code_insee   immo.code_insee PRIMARY KEY,
    -- 'tendue' (agglomération de plus de 50 000 habitants), 'touristique' ou 'non_tendue'
    categorie    text        NOT NULL,
    -- Liste en vigueur, telle que la nomme le fichier (ex. « post décret 22/12/2025 »).
    reference    text        NOT NULL,
    imported_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ref_zone_tendue_categorie_check
        CHECK (categorie IN ('tendue', 'touristique', 'non_tendue'))
);

-- Carte scolaire des collèges publics (ministère de l'Éducation nationale) : collège de
-- secteur par commune ou, dans les communes partagées, par tronçon de voie. Remplacée en
-- bloc par `python -m app.ingestion carte_scolaire`.
CREATE TABLE IF NOT EXISTS immo.ref_carte_scolaire (
    code_insee      immo.code_insee NOT NULL,
    -- Nom de voie normalisé (majuscules sans accent ni ponctuation) ; vide si secteur unique.
    voie            text        NOT NULL DEFAULT '',
    numero_debut    integer,
    numero_fin      integer,
    -- 'P' pairs, 'I' impairs, 'PI' ou NULL : tous les numéros.
    parite          text,
    uai             text        NOT NULL,
    -- Vrai quand toute la commune relève du même secteur.
    secteur_unique  boolean     NOT NULL
);
CREATE INDEX IF NOT EXISTS ref_carte_scolaire_voie_idx
    ON immo.ref_carte_scolaire (code_insee, voie);

-- INSEE Filosofi — revenus disponibles et pauvreté par IRIS. Les valeurs couvertes par le
-- secret statistique ou non diffusées sont NULL.
CREATE TABLE IF NOT EXISTS immo.insee_iris_revenus (
    code_iris          text        NOT NULL,
    annee              smallint    NOT NULL,
    -- Niveau de vie annuel par unité de consommation, en euros.
    revenu_median      integer,
    revenu_q1          integer,
    revenu_q3          integer,
    taux_pauvrete_pct  numeric(4, 1),
    imported_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT insee_iris_revenus_pkey PRIMARY KEY (code_iris),
    CONSTRAINT insee_iris_revenus_code_check CHECK (code_iris ~ '^[0-9AB]{9}$'),
    CONSTRAINT insee_iris_revenus_values_check CHECK (
        (revenu_median IS NULL OR revenu_median > 0)
        AND (taux_pauvrete_pct IS NULL OR taux_pauvrete_pct BETWEEN 0 AND 100)
    )
);

-- INSEE — population municipale de la commune aux trois derniers recensements comparables.
CREATE TABLE IF NOT EXISTS immo.insee_population (
    code_insee      immo.code_insee NOT NULL,
    annee           smallint    NOT NULL,
    population      integer     NOT NULL,
    -- Recensements antérieurs de six et onze ans ; NULL pour une commune créée depuis.
    population_6    integer,
    population_11   integer,
    imported_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT insee_population_pkey PRIMARY KEY (code_insee),
    CONSTRAINT insee_population_values_check CHECK (
        population >= 0 AND coalesce(population_6, 0) >= 0 AND coalesce(population_11, 0) >= 0
    )
);

-- ANCT — périmètres des quartiers prioritaires de la politique de la ville (QPV 2024).
CREATE TABLE IF NOT EXISTS immo.geo_qpv (
    code_qp      text        NOT NULL,
    nom          text        NOT NULL,
    code_insee   text,
    commune      text,
    geom         geometry(MultiPolygon, 4326) NOT NULL,
    imported_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT geo_qpv_pkey PRIMARY KEY (code_qp)
);
CREATE INDEX IF NOT EXISTS geo_qpv_geom_gist ON immo.geo_qpv USING gist (geom);

-- Droits d'accès aux audits complets : une ligne par utilisateur et par adresse achetée.
-- Alimentée après paiement (intégration Stripe à venir) ; sans ligne, l'API ne renvoie
-- que la version « teaser » du rapport.
CREATE TABLE IF NOT EXISTS immo.audit_entitlements (
    user_id     uuid        NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    -- Même clé spatiale que le cache : geohash de précision 9 du point audité.
    geohash     text        NOT NULL,
    origin      text        NOT NULL,
    label       text,
    -- Identifiant BAN de l'adresse, résolu par le serveur à l'achat : le droit suit l'adresse
    -- même si la BAN déplace son point de quelques mètres.
    ban_id      text,
    granted_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT audit_entitlements_pkey PRIMARY KEY (user_id, geohash),
    CONSTRAINT audit_entitlements_origin_check
        CHECK (origin IN ('unit', 'pack', 'subscription', 'admin')),
    CONSTRAINT audit_entitlements_geohash_check CHECK (char_length(geohash) = 9)
);

ALTER TABLE immo.audit_entitlements ADD COLUMN IF NOT EXISTS ban_id text;
CREATE INDEX IF NOT EXISTS audit_entitlements_ban_id_idx
    ON immo.audit_entitlements (user_id, ban_id) WHERE ban_id IS NOT NULL;

-- Crédits d'audit restants (Pack Investisseur) : un crédit débloque une adresse.
CREATE TABLE IF NOT EXISTS immo.user_credits (
    user_id     uuid        NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    credits     integer     NOT NULL DEFAULT 0,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT user_credits_pkey PRIMARY KEY (user_id),
    CONSTRAINT user_credits_non_negative CHECK (credits >= 0)
);

-- Abonnement Pro : accès à toutes les adresses tant qu'il est actif.
CREATE TABLE IF NOT EXISTS immo.user_subscriptions (
    user_id                 uuid        NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    stripe_customer_id      text,
    stripe_subscription_id  text        NOT NULL,
    status                  text        NOT NULL,
    current_period_end      timestamptz,
    -- Date de l'évènement Stripe appliqué : un évènement plus ancien, livré en retard, est ignoré.
    last_event_at           timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT user_subscriptions_pkey PRIMARY KEY (user_id),
    CONSTRAINT user_subscriptions_stripe_id_key UNIQUE (stripe_subscription_id)
);

-- Marque blanche (offre Pro) : nom et logo repris en tête des rapports PDF de l'abonné.
CREATE TABLE IF NOT EXISTS immo.user_branding (
    user_id     uuid        NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    company     text        NOT NULL,
    logo        bytea,
    logo_type   text,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT user_branding_pkey PRIMARY KEY (user_id),
    CONSTRAINT user_branding_company_check CHECK (char_length(company) BETWEEN 1 AND 80),
    CONSTRAINT user_branding_logo_type_check
        CHECK (logo_type IS NULL OR logo_type IN ('image/png', 'image/jpeg')),
    CONSTRAINT user_branding_logo_size_check
        CHECK (logo IS NULL OR octet_length(logo) <= 262144),
    CONSTRAINT user_branding_logo_pair_check CHECK ((logo IS NULL) = (logo_type IS NULL))
);

-- Personnalisation : couleur du bandeau et coordonnées du professionnel.
ALTER TABLE immo.user_branding
    ADD COLUMN IF NOT EXISTS color   text,
    ADD COLUMN IF NOT EXISTS phone   text,
    ADD COLUMN IF NOT EXISTS email   text,
    ADD COLUMN IF NOT EXISTS website text,
    ADD COLUMN IF NOT EXISTS address text;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_branding_color_check') THEN
        ALTER TABLE immo.user_branding
            ADD CONSTRAINT user_branding_color_check
                CHECK (color IS NULL OR color ~ '^#[0-9a-f]{6}$'),
            ADD CONSTRAINT user_branding_contact_check CHECK (
                char_length(coalesce(phone, '')) <= 30
                AND char_length(coalesce(email, '')) <= 120
                AND char_length(coalesce(website, '')) <= 120
                AND char_length(coalesce(address, '')) <= 160
            );
    END IF;
END
$$;

-- Historique des rapports complets consultés : permet à un abonné, qui n'a rien à
-- « débloquer », de retrouver les adresses qu'il a étudiées.
CREATE TABLE IF NOT EXISTS immo.audit_history (
    user_id    uuid        NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
    geohash    text        NOT NULL,
    label      text,
    ban_id     text,
    viewed_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT audit_history_pkey PRIMARY KEY (user_id, geohash),
    CONSTRAINT audit_history_geohash_check CHECK (char_length(geohash) = 9)
);
CREATE INDEX IF NOT EXISTS audit_history_recent_idx
    ON immo.audit_history (user_id, viewed_at DESC);

-- Évènements Stripe déjà traités : Stripe peut livrer deux fois le même évènement.
CREATE TABLE IF NOT EXISTS immo.stripe_events (
    event_id     text        NOT NULL,
    type         text        NOT NULL,
    received_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT stripe_events_pkey PRIMARY KEY (event_id)
);

-- ----------------------------------------------------------------------------
-- 4. Sécurité — RLS, privilèges et policies
-- ----------------------------------------------------------------------------
-- Modèle : immo_app (rôle de service du backend FastAPI) n'est PAS propriétaire
-- des tables ; il y accède uniquement au travers de policies explicites.
-- anon / authenticated (rôles publics de PostgREST) n'ont ni privilège, ni
-- policy, ni même l'usage du schéma : trois verrous indépendants.
ALTER SCHEMA immo OWNER TO postgres;
REVOKE ALL ON SCHEMA immo FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA immo TO immo_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA immo REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA immo REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

DO $$
DECLARE
    tbl text;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'api_reports_cache', 'insee_ssmsi', 'insee_dgfip', 'geo_ips_ecoles', 'geo_sitadel',
        'insee_iris_logement', 'arcep_connectivite', 'geo_bruit_lden', 'geo_osm_poi',
        'ref_loyers', 'ref_zone_tendue', 'ref_carte_scolaire',
        'insee_iris_revenus', 'insee_population', 'geo_qpv',
        'audit_entitlements',
        'user_credits', 'user_subscriptions', 'stripe_events', 'user_branding',
        'audit_history'
    ]
    LOOP
        EXECUTE format('ALTER TABLE immo.%I OWNER TO postgres', tbl);
        EXECUTE format('ALTER TABLE immo.%I ENABLE ROW LEVEL SECURITY', tbl);
        EXECUTE format('ALTER TABLE immo.%I FORCE ROW LEVEL SECURITY', tbl);

        EXECUTE format('REVOKE ALL ON immo.%I FROM PUBLIC, anon, authenticated', tbl);
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON immo.%I TO immo_app', tbl);

        EXECUTE format('DROP POLICY IF EXISTS backend_full_access ON immo.%I', tbl);
        EXECUTE format(
            'CREATE POLICY backend_full_access ON immo.%I '
            'AS PERMISSIVE FOR ALL TO immo_app USING (true) WITH CHECK (true)',
            tbl
        );
    END LOOP;
END
$$;

ALTER FUNCTION immo.purge_expired_reports() OWNER TO postgres;
REVOKE ALL ON FUNCTION immo.purge_expired_reports() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION immo.purge_expired_reports() TO immo_app;

-- Purge horaire des rapports expirés (rejouable : remplace le job du même nom).
SELECT cron.schedule(
    'immo-purge-expired-reports',
    '17 * * * *',
    'SELECT immo.purge_expired_reports()'
);

RESET search_path;
