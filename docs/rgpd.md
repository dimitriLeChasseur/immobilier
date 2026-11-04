# Données personnelles — Audit-immobilier

> Modèle pré-rempli à partir du code ; à valider et compléter (⚠).

| Traitement | Données | Base légale | Durée | Accès |
| --- | --- | --- | --- | --- |
| Compte client | E-mail, mot de passe (haché par Supabase Auth), identifiant Google | Contrat | Jusqu'à suppression du compte (libre-service) | Maksim, backend |
| Achats | Adresses débloquées, offre, identifiants Stripe (pas de carte : chez Stripe) | Contrat, obligation comptable | 10 ans pour les pièces comptables ⚠, droits supprimés avec le compte | Maksim |
| Historique des rapports | Adresses consultées par un abonné | Contrat (fonction demandée) | ⚠ proposer 3 ans | Abonné, Maksim |
| Marque blanche | Nom et logo du professionnel | Contrat | Jusqu'à résiliation | Abonné |
| Aperçus anonymes | Adresse IP (limitation de débit, en mémoire) | Intérêt légitime (sécurité) | Volatile (redémarrage) | Personne |
| E-mails transactionnels | E-mail | Contrat | Journaux SMTP ⚠ | Prestataire SMTP |
| Sauvegardes | Tout ce qui précède | Intérêt légitime (continuité) | ⚠ durée de rétention de `deploy/backup.sh` | Maksim |

Droits : accès, rectification, suppression (libre-service), portabilité ⚠ (export JSON du compte à prévoir), contact ⚠ (adresse à publier). Sous-traitants : Stripe, Cloudflare, hébergeur du VPS, SMTP, Google (connexion). Aucune donnée personnelle n'est envoyée aux sources publiques interrogées : seule l'adresse du bien l'est.
