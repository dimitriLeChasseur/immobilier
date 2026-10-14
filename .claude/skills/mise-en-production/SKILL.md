---
name: mise-en-production
description: Pousser main, attendre la CI qui publie le site, déployer le backend sur le VPS puis vérifier le site et l'API en ligne. Uniquement sur demande explicite de l'utilisateur.
disable-model-invocation: true
---

# Mise en production

Le site (Cloudflare Pages) part en ligne tout seul quand la CI du push sur `main` passe ; le
backend (VPS) part à la main. Les deux doivent finir sur le même commit. Chaque étape est
visible de l'extérieur : ne rien lancer sans que l'utilisateur l'ait demandé dans ce tour.

## 1. Avant de pousser

- `git status` propre, branche `main`, commits relus (`git log origin/main..HEAD`).
- Contrôles locaux passés des deux côtés (commandes dans `CLAUDE.md`).
- Le commit touche-t-il le schéma (`infra/db/init/init.sql`) ? Une instruction lourde (index
  sur une grande table) bloque les écritures pendant sa création : ne pas déployer pendant une
  ingestion planifiée (`deploy/install-cron.sh`, par exemple le 2 du mois à 4 h pour le bruit).
- Une nouvelle variable d'environnement ? Elle doit être dans le `.env` du serveur **avant**
  le déploiement : le script ne touche jamais ce fichier. Le dire à l'utilisateur et attendre.

## 2. Pousser et attendre la CI

```bash
git push origin main
gh run list --branch main --workflow Tests --limit 1      # repérer l'exécution
gh run watch <id> --exit-status
```

Les quatre tâches doivent passer : `Backend et frontend`, `Requêtes SQL sur PostGIS`,
`Parcours d'achat de bout en bout`, puis `Mise en ligne du site`. En cas d'échec, s'arrêter,
lire le journal (`gh run view <id> --log-failed`) et ne pas déployer le backend.

## 3. Déployer le backend

```bash
./scripts/deploy-backend.sh immo@169.58.58.27
```

Le script refuse un arbre de travail modifié, envoie le dernier commit, reconstruit, rejoue le
schéma, interroge la sonde de santé et écrit `.deployed-commit`. Il doit finir sur
`Déployé : <commit>`. Une erreur `psql` signifie que le schéma n'est pas rejouable : le
signaler, ne pas improviser de correctif sur le serveur.

## 4. Vérifier en ligne

Toutes les vérifications sont en lecture seule. Comparer à ce qui est attendu et rapporter
chaque écart.

```bash
SITE=https://audit-immobilier.fr API=https://api.audit-immobilier.fr
for path in / /tarifs /communes /commune/angers-49007; do
  curl -s -o /dev/null -w "$path %{http_code}\n" "$SITE$path"          # 200 attendu
done
curl -s -o /dev/null -w "page inconnue %{http_code}\n" "$SITE/page-inexistante"   # 404
curl -s -o /dev/null -w "commune inconnue %{http_code}\n" "$SITE/commune/zzz-99999" # 404
curl -s -o /dev/null -w "www %{http_code} %{redirect_url}\n" https://www.audit-immobilier.fr/  # 301
curl -s "$API/api/health/ready"                                     # {"status":"ready"}
curl -s "$API/api/v1/sources"                                       # liste des sources
# Rapport d'exemple : complet ("access": "demo"), sources en échec listées
curl -s "$API/api/v1/audit?lat=47.46976&lon=-0.553891&ban_id=49007_7050_00010" \
  | python3 -c "import sys,json; m=json.load(sys.stdin)['meta']; print(m['access'], m['report_version'], m['failed_sources'])"
# Aperçu d'une autre adresse : des valeurs masquées
curl -s "$API/api/v1/audit?lat=47.47408&lon=-0.55107" | grep -c 'LOCKED'
```

À contrôler en plus selon le contenu du commit :

- **Prix ou offres** : `curl -s $SITE/tarifs | grep -o '[0-9]*,[0-9]* €' | sort | uniq -c`
  et les prix des données structurées sur l'accueil (`"price"`).
- **Format du rapport** : `report_version` du rapport d'exemple égale à celle de
  `backend/app/core/config.py`.
- **Version du site** : le nom des fichiers `/assets/index-*.js` de l'accueil a changé.

## 5. Compte rendu

Commit poussé, résultat de chaque tâche CI, sortie du déploiement, puis un tableau des
vérifications (attendu, obtenu). Signaler les sources en échec dans le rapport d'exemple, en
précisant si la panne vient du service public lui-même.
