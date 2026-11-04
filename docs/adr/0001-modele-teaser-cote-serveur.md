# ADR 0001 — Masquage de l'aperçu côté serveur

- **Statut** : accepté (reconstitué le 04/11/2026 à partir du code existant)
- **Contexte** : le rapport complet est payant ; un masquage dans le navigateur se contourne en lisant la réponse réseau.
- **Décision** : l'API remplace les valeurs réservées par `***LOCKED***` (`backend/app/services/teaser.py`) selon une liste blanche par source ; tout nouveau champ est masqué par défaut. Le flou du frontend n'est qu'un habillage.
- **Conséquences** : chaque nouvelle source ou champ visible passe par la skill `ajouter-une-source` et décide explicitement de sa visibilité ; les chiffres de commune déjà publics restent en clair.
