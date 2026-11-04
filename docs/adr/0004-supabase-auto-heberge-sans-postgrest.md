# ADR 0004 — Supabase auto-hébergé, sans API REST automatique

- **Statut** : accepté (reconstitué le 04/11/2026 depuis le README)
- **Contexte** : besoin de l'authentification de Supabase sans exposer la base à une API générique.
- **Décision** : image Supabase auto-hébergée (Auth, PostgreSQL + PostGIS, Studio local) ; aucune instance PostgREST déployée ; tables dans le schéma `immo` avec RLS ; le backend se connecte avec le rôle `immo_app`, sans DDL.
- **Conséquences** : toute lecture passe par FastAPI ; Studio n'écoute que sur `127.0.0.1` (tunnel SSH).
