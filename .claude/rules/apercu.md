---
paths:
  - "backend/app/services/teaser.py"
  - "backend/app/schemas/audit.py"
  - "backend/tests/test_teaser.py"
  - "frontend/src/lib/teaser.ts"
  - "frontend/src/components/Locked*.vue"
---

# Aperçu gratuit et masquage

Une fuite ici livre gratuitement l'audit payant.

- Toute valeur payante est remplacée par `***LOCKED***` côté serveur, dans `teaser.py`, avant
  la sérialisation. Le flou du frontend n'est qu'un habillage : ne jamais compter dessus.
- Les données des sources passent par une liste blanche (`_CLEAR_KEYS`) : un nouveau champ est
  masqué par défaut. Ajouter une clé à `_CLEAR_KEYS` ou à `_PARTIAL` ne se justifie que pour
  une accroche (un nombre, un rayon, une méthode), jamais pour un résultat propre à l'adresse.
- `mask_meta` et `mask_report` ne masquent que ce qu'ils nomment : un champ ajouté à
  `ReportMeta`, `AuditReport`, `Location` ou `SourceResult` passe en clair dans l'aperçu. Le
  masquer explicitement, ou s'assurer qu'il est réellement public et l'ajouter à
  `REVIEWED_FIELDS` (`test_teaser.py`), qui échoue tant qu'un champ n'a pas été examiné.
- Tout changement de masquage a son test dans `backend/tests/test_teaser.py`.
