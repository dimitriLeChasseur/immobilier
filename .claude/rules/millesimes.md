---
paths:
  - "backend/app/ingestion/**"
  - "backend/app/services/providers/rental_rules.py"
---

# Données datées

- Les adresses des fichiers INSEE (revenus, population, quartiers prioritaires) changent à
  chaque millésime : les mettre à jour dans `backend/app/ingestion/datasets.py`, avec le
  repère national codé en dur qui va avec. Le MCP `datagouv` permet de trouver l'adresse du
  nouveau fichier et sa date de publication.
- La liste d'encadrement des loyers de `rental_rules.py` est codée en dur d'après
  service-public.gouv.fr : la relire à chaque nouveau décret et mettre à jour la date de
  vérification, ici et dans la section « Limites connues » du README.
