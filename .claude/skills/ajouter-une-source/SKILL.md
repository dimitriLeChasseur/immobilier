---
name: ajouter-une-source
description: Liste de contrôle pour brancher une nouvelle source de données dans l'audit (fournisseur backend, masquage de l'aperçu, carte, PDF, test de fumée, cache), ou pour ajouter un champ visible à une source existante. À utiliser dès qu'une donnée nouvelle doit apparaître dans le rapport.
---

# Ajouter une source de données

Une source touche une dizaine de fichiers. En oublier un ne casse en général aucun test :
la donnée est simplement masquée, absente du PDF ou jamais surveillée. Suivre la liste dans
l'ordre et cocher chaque ligne dans le compte rendu final. Modèle récent à imiter : la source
`quartier` (`NeighbourhoodProvider`, commit `ce30c48`).

## 0. Avant d'écrire

- La source est **gratuite et ouverte** (règle du projet). Noter sa licence, son producteur,
  son millésime et sa limite de débit : le MCP `datagouv` donne la fiche du jeu de données ou
  de l'API, la skill `research` étudie sa documentation officielle.
- Choisir entre **appel en direct** (API publique) et **référentiel ingéré** (table du schéma
  `immo`, chargée par `app.ingestion`). Un fichier national statique ou une API lente se
  charge en base.
- Choisir le **nom de la source** : court, en français, en `snake_case` (`taxe_fonciere`).
  C'est une clé du contrat de l'API : il ne changera plus.
- Décider ce qui reste **gratuit dans l'aperçu** : en règle générale, les chiffres de la
  commune déjà publiés sur les fiches communales ; tout ce qui est propre à l'adresse est payant.

## 1. Backend

- [ ] **Fournisseur** : `backend/app/services/providers/<module>.py`, une classe avec
  `name = "<source>"` et `async def fetch(self, ctx: AuditContext) -> ProviderData` (protocole
  dans `providers/base.py`). Lever `NoDataError` quand il n'y a rien pour l'adresse ; renvoyer
  `missing` pour une réponse partielle (`gather_parts`).
- [ ] **Appels HTTP** par `HttpClient` avec un nom de source propre au service appelé : il porte
  le coupe-circuit et le quota par minute (`source_quotas` dans `core/config.py` si le service
  annonce une limite).
- [ ] **Référentiel ingéré** : table et index dans `infra/db/init/init.sql` (rejouable), droits
  du rôle `immo_app`, chargement dans `backend/app/ingestion/` et `repositories/ingestion.py`,
  lecture dans `repositories/reference.py`, entrée dans `deploy/install-cron.sh` si la donnée
  est rafraîchie.
- [ ] **Composition** : ajouter le fournisseur à la liste de `build_audit_service`
  (`backend/app/container.py`). Durée de cache propre à la source, si besoin : `source_ttls`.
- [ ] **Aperçu gratuit** : `backend/app/services/teaser.py`. Ajouter les clés laissées en clair
  dans `_CLEAR_KEYS` (tout le reste est masqué), une à une même quand toute la source est
  publique : un champ ajouté plus tard reste ainsi masqué par défaut.
- [ ] **Synthèse** (facultatif) : une règle dans `backend/app/services/synthesis.py` si la
  donnée mérite une alerte ou un point fort.
- [ ] **Test de fumée** : clés attendues dans `EXPECTED_KEYS` (`backend/app/smoke.py`) ;
  `may_be_empty` si la source est vide sur une adresse de référence.
- [ ] **Version du rapport** : incrémenter `report_version` (`backend/app/core/config.py`).

## 2. Frontend

- [ ] **Type** : interface `<Nom>Data` et entrée dans `SourceDataMap`
  (`frontend/src/types/audit.ts`). `SourceName` en découle.
- [ ] **Libellés** : entrée dans `SOURCE_INFO` (`frontend/src/lib/sources.ts`) avec `title`
  et `emptyText` ; mettre à jour `DATA_SOURCES` si le producteur est nouveau.
- [ ] **Étapes de chargement** : ajouter la source à l'étape qui convient dans
  `frontend/src/lib/steps.ts`.
- [ ] **Carte** : composant `frontend/src/components/cards/<Nom>Card.vue`, logique de mise en
  forme dans `frontend/src/lib/<module>.ts` (testable sans DOM), branchement dans
  `AuditDashboard.vue` par `<SourceCard v-bind="card('<source>')">`, dans la bonne section.
- [ ] **Accroche de l'aperçu** : phrase dans `HOOKS` (`frontend/src/lib/teaser.ts`), qui prouve
  que l'analyse a eu lieu sans rien révéler de payant.
- [ ] **PDF** : lignes dans la section qui convient de `frontend/src/lib/report.ts`.
- [ ] **Checklist de contre-visite** (facultatif) : `frontend/src/lib/checklist.ts`.
- [ ] **Page d'accueil** : si la donnée vaut argument de vente, une ligne dans `CONTENTS`
  (`frontend/src/components/HomeIntro.vue`).

## 3. Tests

- [ ] Backend : `backend/tests/test_<module>.py` couvre le cas nominal, la réponse vide
  (`NoDataError`), la réponse partielle et une erreur de la source.
- [ ] Masquage : un cas dans `backend/tests/test_teaser.py` prouve que les valeurs payantes ne
  sortent pas en clair.
- [ ] Référentiel ingéré : requête testée dans `backend/tests/test_integration_sql.py`.
- [ ] Frontend : `frontend/tests/<module>.test.ts` pour la mise en forme et la carte.
- [ ] Contrôles complets, couverture comprise : agent `verificateur`, puis `gardien-du-projet`
  sur le diff.

## 4. Documentation

- [ ] README : liste des sources (section « Architecture ») et, pour un référentiel, section
  « Données ingérées » avec la commande d'ingestion.
- [ ] Mentions des sources dans les pages légales si la licence l'exige
  (`frontend/src/lib/legalContent.ts`).

## Compte rendu

Terminer par la liste ci-dessus, chaque ligne marquée faite, sans objet (avec la raison) ou
restant à faire. Signaler toute ingestion à lancer en production : le déploiement rejoue le
schéma mais ne charge aucune donnée.
