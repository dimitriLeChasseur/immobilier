# Inventaire des secrets — Audit-immobilier

> Noms seulement. Serveur : `/opt/immobilier/.env` (VPS 2) ; front : variables du projet Cloudflare Pages ; CI : secrets GitHub. `VITE_*` = **public**.

| Secret | Où | Rotation |
| --- | --- | --- |
| `POSTGRES_PASSWORD`, `IMMO_APP_DB_PASSWORD` | `.env` | ⚠ |
| `JWT_SECRET`, `ANON_KEY`, `SERVICE_ROLE_KEY`, `PG_META_CRYPTO_KEY` | `.env` (générés par `scripts/generate-env.sh`) | Rotation = déconnexion de tous les utilisateurs ⚠ |
| `SMTP_USER`, `SMTP_PASS` | `.env` | ⚠ |
| `GOOGLE_CLIENT_ID`, `GOOGLE_SECRET` | `.env` | ⚠ |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRO_TAX_RATE_ID` | `.env` | ⚠ (clés de test en production aujourd'hui) |
| `ORS_API_KEY` | `.env` (facultatif) | ⚠ |
| `CLOUDFLARE_TURNSTILE_SECRET_KEY` | `.env` | ⚠ |
| `BACKUP_PASSPHRASE` | `.env` + gestionnaire de mots de passe de Maksim (indispensable à la restauration) | Jamais perdue |
| `SONAR_DB_PASSWORD`, `SONAR_ADMIN_PASSWORD`, `SONAR_TOKEN` | `.env` local | — |
| `VITE_SUPABASE_ANON_KEY`, `VITE_TURNSTILE_SITE_KEY` | Public (front) | — |
