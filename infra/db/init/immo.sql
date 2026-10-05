-- Socle du projet : extensions spatiales, rôle applicatif à privilèges réduits
-- et schéma privé du backend. Les tables sont créées à l'étape 2 (migrations).
\set app_pass `echo "$IMMO_APP_DB_PASSWORD"`

CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;

-- Rôle utilisé par FastAPI : ni superutilisateur, ni contournement de la RLS.
CREATE ROLE immo_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD :'app_pass';

-- Schéma non exposé par PostgREST (cache des API, référentiels statiques).
-- immo_app n'en est pas propriétaire : il ne peut ni créer ni supprimer d'objets.
CREATE SCHEMA IF NOT EXISTS immo;
GRANT USAGE ON SCHEMA immo TO immo_app;

GRANT USAGE ON SCHEMA extensions TO immo_app;
ALTER ROLE immo_app SET search_path = immo, public, extensions;
