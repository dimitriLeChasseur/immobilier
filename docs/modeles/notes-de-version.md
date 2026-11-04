# Notes de version — modèle

Tenir `CHANGELOG.md` à la racine, la version la plus récente en haut, format [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) :

```markdown
## [1.4.0] — 2026-11-04
### Ajouté
- Ce que l'utilisateur peut faire de nouveau, en une phrase.
### Modifié
- Comportement changé (et pourquoi si ce n'est pas évident).
### Corrigé
- Bug corrigé, du point de vue de l'utilisateur.
### Sécurité
- Dépendance mise à jour, faille corrigée (sans détail exploitable avant déploiement).
```

Règles : une entrée par changement visible ; les changements internes sans effet utilisateur n'y figurent pas ; la version suit le versionnage sémantique ; l'étiquette Git `vX.Y.Z` est posée au déploiement.
