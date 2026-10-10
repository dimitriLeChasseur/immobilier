"""Configuration minimale des tests : `uv run pytest` fonctionne sans variable d'environnement.

Les deux réglages obligatoires de l'application reçoivent une valeur factice, sans écraser
celles de l'environnement (la CI et les tests d'intégration fournissent les leurs). Aucune
connexion n'est ouverte avec : les tests SQL ne s'exécutent qu'avec IMMO_TEST_DATABASE_URL.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test")
