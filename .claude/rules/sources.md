---
paths:
  - "backend/app/services/providers/**"
  - "backend/app/services/audit_service.py"
  - "backend/app/core/http.py"
  - "backend/app/schemas/audit.py"
---

# Sources de données

- Brancher une source ou ajouter un champ visible : suivre la skill `ajouter-une-source`.
- Aucune source n'ouvre sa propre connexion HTTP : tout appel passe par le client de
  `app/core/http.py` (délai strict, coupe-circuit par source, erreurs typées).
- `fetch` lève `NoDataError` quand la source n'a rien pour cette localisation, `SourceError`
  quand elle est en échec : la distinction s'affiche dans le rapport.
- Un champ ajouté, renommé ou retiré dans les données renvoyées impose d'incrémenter
  `report_version` dans `backend/app/core/config.py`, sinon le cache sert l'ancien format
  pendant sept jours.
- Respecter la licence de la source : ODbL (OpenStreetMap, indice ATMO) impose l'attribution,
  dans les pages légales (`frontend/src/lib/legalContent.ts`) et là où la licence le demande ;
  une source sans licence ouverte ne s'intègre pas.
