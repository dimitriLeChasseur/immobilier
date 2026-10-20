# Audit Immobilier

Une adresse française, une vingtaine de sources publiques interrogées, un rapport : ce
glossaire fixe les mots du produit, de l'interface au code, pour qu'un même concept porte
toujours le même nom.

## Le rapport

**Rapport** :
Ce que l'application produit et vend pour une adresse : un bloc par source, une synthèse, un
export PDF. « Audit » ne subsiste que dans le nom de la marque et les textes du site.
_Éviter_ : audit, résultat, analyse, diagnostic (réservé au DPE), fiche (réservé aux fiches
communales)

**Aperçu** :
Le rapport tel qu'un visiteur le reçoit sans droit sur l'adresse : chiffres de la commune et
accroches en clair, valeurs propres à l'adresse masquées.
_Éviter_ : teaser, version gratuite, rapport flouté

**Rapport complet** :
Le rapport sans aucune valeur masquée, servi à qui a un droit sur l'adresse.
_Éviter_ : audit complet (sauf dans les textes du site), rapport premium, version payante

**Rapport d'exemple** :
Le rapport d'une adresse fixe, servi complet à tous pour montrer ce que contient le rapport complet.
_Éviter_ : démo, adresse de démonstration

**Accroche** :
Une information laissée visible dans l'aperçu pour prouver que l'adresse a bien été analysée,
sans livrer le résultat (un nombre de ventes, un rayon).
_Éviter_ : hook, teaser

**Synthèse** :
Les alertes et points forts les plus marquants du rapport, en tête de celui-ci.

**Constat** :
Une alerte ou un point fort de la synthèse : un thème, un titre, un détail.
_Éviter_ : finding, insight

**Rapport partiel** :
Un rapport dont au moins une source n'a pas (entièrement) répondu ; il reste exploitable.

## Les sources

**Source** :
Un jeu de données public interrogé pour le rapport, et le bloc du rapport qui en sort ; son nom
(`dvf`, `quartier`, `taxe_fonciere`…) ne change plus une fois publié.
_Éviter_ : fournisseur, provider, API (une source peut être une base chargée à l'avance)

**Source vide** :
Une source qui a répondu mais n'a rien pour cette localisation.
_Éviter_ : source en erreur

**Source en échec** :
Une source qui n'a pas répondu ou a répondu de façon inexploitable.
_Éviter_ : source vide

**Référentiel** :
Une source chargée à l'avance en base depuis un fichier national, plutôt qu'interrogée en
direct à chaque rapport.
_Éviter_ : dataset, table de référence

**Millésime** :
L'édition datée d'un jeu de données public (revenus 2021, population 2022).
_Éviter_ : version, année des données

**IRIS** :
Le découpage statistique de l'INSEE en îlots d'environ 2 000 habitants, maille du profil du
quartier.

**Quartier prioritaire** :
Un quartier prioritaire de la politique de la ville (QPV), au sens de l'État.
_Éviter_ : quartier (seul), quartier sensible

**Chiffres de la commune** :
Les données publiées à l'échelle de la commune ou d'un territoire plus large qui la contient
(intercommunalité, département, bassin d'air) : loyers, taxe foncière, délinquance, fibre,
émissions du territoire. Elles ne disent rien de propre à l'adresse et restent donc en clair
dans l'aperçu.

**Épisode de pollution** :
Un jour où le seuil d'information ou d'alerte d'un polluant est dépassé sur une zone
(département, bassin d'air, région), au sens des procédures préfectorales.
_Éviter_ : pic de pollution, alerte (seul : c'est l'un des deux niveaux)

**Inventaire** :
Le bilan annuel de ce qu'un territoire émet (polluants, gaz à effet de serre) et consomme
(énergie), par secteur, publié par millésime par les associations de surveillance de l'air.
_Éviter_ : bilan carbone, émissions (seul)

**Fiche communale** :
La page publique d'une commune, qui présente ses chiffres sans adresse.
_Éviter_ : page commune, fiche ville

**Mode rue** :
Un rapport portant sur une voie entière plutôt que sur un numéro, quand l'adresse exacte n'est
pas connue.

## Les offres et l'accès

**Offre** :
Ce que le site vend : Contre-Visite, Pack Investisseur ou Pro. Le prix de chaque offre est
fixé par le serveur.
_Éviter_ : formule, plan, abonnement (réservé à Pro)

**Contre-Visite** :
L'offre à l'unité : le rapport complet d'une adresse, payé une fois. Le mot désigne l'offre
seulement, jamais la visite du bien.
_Éviter_ : achat à l'unité, audit unitaire

**Seconde visite** :
La nouvelle visite d'un bien avant de faire une offre, que la checklist du rapport prépare.
_Éviter_ : contre-visite (réservé à l'offre)

**Pack Investisseur** :
L'offre de dix crédits payés une fois, sans date limite.
_Éviter_ : pack (seul), lot

**Pro** :
L'offre par abonnement mensuel, avec marque blanche et un plafond d'adresses nouvelles par jour.
_Éviter_ : abonnement premium, offre agence

**Crédit** :
Une unité du Pack Investisseur, dépensée pour débloquer une adresse.
_Éviter_ : jeton, token, audit restant

**Droit** :
L'accès d'un compte au rapport complet d'une adresse, ouvert par un paiement confirmé, un crédit
ou l'abonnement Pro.
_Éviter_ : entitlement, licence, achat

**Débloquer** :
Ouvrir un droit sur une adresse.
_Éviter_ : acheter (un crédit ne s'achète pas à l'adresse), déverrouiller

**Plafond Pro** :
Le nombre maximal d'adresses nouvelles qu'un abonné Pro peut ouvrir en 24 heures.
_Éviter_ : quota (réservé aux limites techniques des sources et des visiteurs)

**Marque blanche** :
Le nom et le logo d'un abonné Pro en tête de ses rapports PDF.
_Éviter_ : branding, personnalisation

## Les personnes

**Visiteur** :
Une personne sans compte ; elle ne reçoit que l'aperçu et un nombre limité de rapports par heure.
_Éviter_ : anonyme, invité

**Utilisateur** :
Une personne avec un compte, qu'elle ait payé ou non.
_Éviter_ : membre, inscrit, client (réservé à qui a payé)

**Client** :
Un utilisateur qui a payé au moins une fois : Contre-Visite, Pack Investisseur ou abonnement Pro.
_Éviter_ : acheteur, utilisateur (plus large)

**Abonné** :
Un client dont l'abonnement Pro est en cours.
_Éviter_ : client Pro, professionnel
