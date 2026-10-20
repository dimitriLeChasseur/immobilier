# Atmo Data (Atmo France) : API « admindata » et WFS public

Recherche du 2026-10-20. Sources primaires uniquement (spec OpenAPI, notices et FAQ d'Atmo
France, CGU, Légifrance, data.gouv.fr), plus des requêtes réelles sur le WFS public sans
compte. Aucun identifiant n'a été utilisé : tout ce qui ne se voit qu'avec un jeton est
marqué **non vérifié**. Les numéros entre crochets renvoient à la liste des sources en fin
de document.

## Résumé

- L'API v2 (`https://admindata.atmo-france.org/api/v2/data/...`, jeton JWT valable 24 h)
  expose 5 routes : indice ATMO, épisodes sur 3 jours, historique des épisodes, inventaires
  d'émissions (avec les consommations d'énergie), indice pollen [1].
- **Le WFS public sans compte** (`https://data.atmo-france.org/geoserver/ows`) expose déjà
  les quatre thèmes : `alrt:*` (épisodes), `emissions:*` (inventaires et consommations),
  `ind_pol:*` (pollen), en plus de `ind:ind_atmo_2021` déjà utilisé [5].
- Ce que l'API apporte en plus, d'après la notice : l'**historique** des indices ATMO et
  pollen (« année N-1 complète » / « un an glissant ») [3]. Le WFS public ne garde que la
  fenêtre J à J+2 (vérifié). La spec v2 dit au contraire que l'historique de l'indice ATMO se
  limite aux « trois derniers jours » [1] : c'est **contradictoire, à tester avec le jeton**.
- Licence ODbL, mention « Source : Atmo France / AASQA » obligatoire [1][4]. Les CGU ne
  disent rien sur l'usage commercial ni sur des quotas [4].
- **Recommandation** : rester sur le WFS public sans secret et ajouter en priorité les
  **inventaires EPCI** (millésimes 2010, 2018 et 2022, par secteur, avec les consommations
  d'énergie) : ce sont des données stables, adaptées à un achat et faciles à mettre en
  cache longtemps. L'historique des épisodes (WFS `alrt:alrt`) peut s'y ajouter, avec
  prudence. N'utiliser l'API (et donc un secret côté serveur) que si un essai avec le jeton
  confirme un an d'historique de l'indice ATMO par commune : un « nombre de jours dégradés
  sur 12 mois » serait alors calculable. Le pollen du jour est éphémère : il a peu de valeur
  pour un achat.

## Authentification et conditions

### Obtention du jeton

- Inscription sur `https://admindata.atmo-france.org/inscription-api`. La demande est validée
  à la main par un administrateur, puis l'utilisateur crée son mot de passe [2][6]. Parmi les
  motifs proposés dans le formulaire, on trouve « Professionnel : Intégrer dans une
  application tierce » [6].
- `POST https://admindata.atmo-france.org/api/login`, corps JSON
  `{"username": "...", "password": "..."}` [1]. Le schéma déclare `required: ["userName"]`
  alors que la propriété s'appelle `username` (incohérence de casse dans la spec).
- Durée de validité : **24 heures** d'après la spec v2 (« Le token a une durée de validité de
  24 heures ») [1]. La FAQ de 2023 parlait d'une heure [2]. La spec v2 fait foi, mais c'est
  non vérifié en pratique.
- Renouvellement : pas de jeton de rafraîchissement documenté. On rappelle `/api/login` à
  l'expiration [2].
- Format de la réponse de `/api/login` : la spec ne le documente pas (`responses.default`
  vide) [1]. La FAQ évoque un champ « value » à recopier dans l'en-tête [2]. **Non vérifié**
  (nom exact du champ, présence d'une date d'expiration).
- En-tête : `Authorization: Bearer <jeton>` (schéma de sécurité `http`/`bearer`/`JWT`) [1].
  Sans jeton, l'API répond `401 {"code":401,"message":"JWT Token not found"}` (vérifié sur
  `/api/feeds`).

### Quotas et bonnes pratiques

- Aucun quota chiffré n'est publié, ni dans la spec, ni dans la FAQ, ni dans les CGU
  [1][2][4]. **Non vérifié** : existence d'une limite de débit côté serveur.
- La FAQ demande [2] :
  - d'interroger l'API « 1 à 2 fois par jour », hors de la fenêtre 13 h–15 h (heure de Paris)
    où les flux se mettent à jour ;
  - de mettre en cache plutôt que d'interroger à chaque usage ;
  - de découper l'historique en tranches de deux semaines ;
  - de ne pas demander les géométries (`with_geom=false` en v2, `?withGeom=false` en v1).
- Mise à jour quotidienne : à 14 h locales pour l'indice ATMO et les épisodes, à 12 h pour
  le pollen [3]. Pour l'outre-mer, la FAQ indique « à partir de 18h00 » [2].

### Licence, attribution, usage commercial

- ODbL 1.0 pour toutes les données d'Atmo Data [1][3][4]. La page data.gouv.fr du jeu
  « Atmo Data » porte `odc-odbl` [7]. Celle du jeu « Données émissions » affiche
  `notspecified` [8], mais la notice et les CGU couvrent les émissions par l'ODbL [3][4].
- Mention exigée : « Source : Atmo France / AASQA » (spec v2) [1]. Les CGU écrivent
  « Source des données : Atmo France/AASQA » [4]. La FAQ demande aussi de nommer l'AASQA
  source, présente dans chaque enregistrement (`aasqa`, `source`) [2].
- Usage commercial : les CGU ne l'abordent pas [4]. L'ODbL l'autorise, sous réserve
  d'attribution et de partage à l'identique des bases dérivées rendues publiques
  (lecture du texte de la licence, pas une position d'Atmo France). Le rapport est une
  « œuvre produite » : l'attribution y suffit. Le cache interne n'est pas diffusé.
  L'attribution existante dans `frontend/src/lib/legalContent.ts` doit couvrir les nouveaux
  jeux.
- Responsabilité : l'utilisateur est « seul responsable de l'utilisation qu'il fait des
  résultats obtenus ». Atmo France n'est pas responsable des erreurs ni des indisponibilités
  [4].

## Thème 1 : indice ATMO (qualité de l'air)

**Texte réglementaire** : arrêté du 10 juillet 2020 relatif à l'indice de la qualité de l'air
ambiant (JO du 29 juillet 2020), applicable au 1er janvier 2021 [9].

- Six classes : Bon, Moyen, Dégradé, Mauvais, Très mauvais, Extrêmement mauvais.
- Cinq polluants : SO2, NO2, O3, PM10, PM2.5. L'indice est le sous-indice le plus dégradé.
- Zones qui couvrent intégralement chaque EPCI.
- Seuils de l'annexe I, en µg/m³ (bornes hautes de Bon, Moyen, Dégradé, Mauvais, Très
  mauvais) :

  | Polluant | Bornes |
  |---|---|
  | PM2.5 | 10, 20, 25, 50, 75 |
  | PM10 | 20, 40, 50, 100, 150 |
  | NO2 | 40, 90, 120, 230, 340 |
  | O3 | 50, 100, 130, 240, 380 |
  | SO2 | 100, 200, 350, 500, 750 |

Version consolidée actuelle non contrôlée : seule la version JORF initiale a été lue.

**Route API v2** : `GET /api/v2/data/indices/atmo` [1]. Paramètres :

| Paramètre | Valeurs |
|---|---|
| `format` | `geojson` (défaut) ou `csv` |
| `date` | AAAA-MM-JJ |
| `date_historique` | début de période ; la spec précise « seuls les trois derniers jours sont disponibles » |
| `code_zone` | code INSEE commune ou EPCI, un ou plusieurs |
| `aasqa` | code de l'AASQA, `01` à `94` |
| `code_qualificatif` | 0 à 7 |
| `bounding_box` | `xmin ymin xmax ymax` |
| `bounding_box_srs` | 4326 par défaut |

**Champs** [3], confirmés par l'exemple `/exemple_indices.json` [1] :

- identification de la zone : `date_ech` (date de validité), `date_dif` (date de diffusion),
  `code_zone`, `lib_zone`, `type_zone` (`commune` ou `EPCI`) ;
- indice : `code_qual` (1 à 6 ; 0 absent ; 7 événement), `lib_qual`, `coul_qual` ;
- sous-indices : `code_no2`, `code_so2`, `code_o3`, `code_pm10`, `code_pm25` ;
- producteur : `source`, `aasqa` ;
- position : `x_wgs84`, `y_wgs84`, `x_reg`, `y_reg`, `epsg_reg` ;
- concentrations `conc_*` en µg/m³ : champs **facultatifs**, selon l'AASQA.

Clé primaire `(date_ech, code_zone)`. Une valeur publiée en J+1 est remplacée par la
prévision du jour, puis par l'observé de la veille [3].

**Couverture.** Toutes les AASQA, outre-mer compris. Le WFS du 2026-10-20 renvoie des
indices pour les 18 AASQA (vérifié). Granularité selon la région, mesurée ce jour-là :

- surtout à la commune ;
- **à l'EPCI uniquement** pour Air Breizh (61 EPCI) et Atmo Occitanie (164 EPCI) ;
- mixte pour Pays de la Loire et Nouvelle-Aquitaine.

Le code actuel gère déjà ce repli vers l'EPCI.

**Profondeur.**

- Notice : « l'année N-1 complète plus l'année en cours jusqu'à J+1 voire J+2 » [3].
- Spec v2 : trois derniers jours pour `date_historique` [1]. **Contradictoire, à tester.**
- WFS public `ind:ind_atmo_2021` : J à J+2 seulement (3 lignes pour Valence, vérifié).

**Limite d'usage.** La notice dit que l'indice ATMO « ne permet pas d'évaluer la situation
de la qualité de l'air à l'échelle annuelle ou de dégager des tendances ; pour cela, il faut
se référer aux concentrations » [3]. Un « nombre de jours dégradés par an » tiré de l'indice
reste un indicateur de communication, et doit être présenté comme tel.

## Thème 2 : épisodes de pollution

**Cadre** : arrêté du 7 avril 2016 relatif au déclenchement des procédures préfectorales en
cas d'épisodes de pollution de l'air ambiant (JO du 9 avril 2016, modifié) [10] ; seuils
d'information et d'alerte du code de l'environnement [3]. Version consolidée non relue en
entier : seul un extrait de recherche Légifrance a été consulté, donc partiellement vérifié.

**Niveaux** (`etat`) [1][3] :

| Valeur | Couleur | Statut |
|---|---|---|
| `PAS DE DEPASSEMENT` | #19FF19 | |
| `INFORMATION ET RECOMMANDATION` | #FFCE19 | réglementaire |
| `ALERTE SUR PERSISTANCE` | #FF7419 | non réglementaire : niveau d'information prévu pour J et J+1 |
| `ALERTE` | #FF1919 | réglementaire |

**Polluants** : NO2, SO2, PM10, PM2.5, O3 (énumération de la spec) [1]. La notice dit que les
épisodes se déclenchent sur 4 polluants (O3, NO2, SO2, PM10) [3], mais les données
contiennent aussi des épisodes PM2.5 (`code_pol` 6001, 660 lignes, vérifié).

**Échelle géographique.**

- Département (code INSEE) dans la plupart des régions [1][3].
- **Bassins d'air** en Auvergne-Rhône-Alpes : codes `2000` à `2011` listés dans la spec [1],
  mais le flux contient `2000` à `2020` (vérifié).
- **Région entière** pour l'Île-de-France : `code_zone = "11"`, `lib_zone = "ILE-DE-FRANCE"`
  (vérifié). Ce code est le même que celui du département de l'Aude, voir les pièges.

**Routes API v2** [1] :

- `GET /api/v2/data/episodes/3jours` : J-1, J0 et J+1 (`echeance` -1/0/1).
- `GET /api/v2/data/episodes/historique` : « constatés sur l'année passée » ; `date`
  obligatoire, `date_historique` facultatif.
- Filtres communs : `aasqa`, `code_zone`, `polluant`, `type_episode`, `bounding_box`.

**Champs** : `code_zone`, `lib_zone`, `date_ech`, `date_dif`, `code_pol` (code UE), `lib_pol`,
`etat`, et dans le flux 3 jours `couleur`, `com_court`, `com_long` [3].

**Profondeur.**

- Notice : du 1er janvier N-1 à la veille [3], et « 1 an glissant démarrant au 1er janvier
  2018 » dans son tableau récapitulatif.
- WFS public `alrt:alrt` (vérifié) : 19 768 lignes, de 2008 à 2026. L'historique est **très
  inégal** : 3 256 jours d'épisode réels au total, mais 828 en 2025 et 900 en 2026 contre
  92 en 2024. La plupart des AASQA n'alimentent ce flux que depuis 2025. Ce n'est pas une
  série comparable d'une année sur l'autre.

## Thème 3 : indice pollen

**Texte de référence.** Aucun arrêté ministériel trouvé pour cet indice : **non vérifié**
qu'il n'en existe pas. D'après la notice, l'échelle est « inspirée de l'indice ATMO » et les
seuils des sous-indices s'appuient sur les travaux de l'EAACI (Académie européenne
d'allergologie) [3].

**Échelle** : 0 Indisponible, 1 Très faible, 2 Faible, 3 Modéré, 4 Élevé, 5 Très élevé,
6 Extrêmement élevé. `alerte = true` à partir de `code_qual = 4` [1][3].

**Taxons** : aulne, bouleau, olivier, graminées, armoise, ambroisie, modélisés via
Copernicus [3]. Saisonnalité d'après la notice :

| Taxon | Période |
|---|---|
| Aulne | janvier à juin |
| Bouleau | mars à juin |
| Olivier | avril à juin, zones méditerranéennes |
| Graminées | mars à août |
| Armoise | juin à octobre |
| Ambroisie | juin à octobre |

**Producteur.** Les AASQA, avec un modèle statistique (apprentissage automatique sur 8 ans
de mesures et de météo) et un krigeage [3]. Les données antérieures au 1er avril 2025
viennent de la base départementale du **RNSA**, avec une autre échelle (0 à 3) et une
vingtaine de taxons, selon la page data.gouv.fr d'AtmoSud [11]. Il y a donc rupture de série
au 1er avril 2025.

**Couverture.** **Métropole et Corse uniquement**, pas d'outre-mer [3]. Au 2026-10-20, 13
producteurs ; l'Occitanie est servie sous `source = "Atmo France"` (Toulouse, Montpellier
vérifiés).

**Granularité** : commune [3]. Seuls les codes de commune entière sont présents : `75056`,
`69123` et `13055` existent, `75101`, `69381` et `13201` n'existent pas (vérifié).

**Route API v2** : `GET /api/v2/data/indices/pollens` [1]. Paramètres : `date`,
`date_historique`, `code_zone` (INSEE commune), `aasqa`, `code_qualificatif`, `alerte`,
`with_geom` (faux par défaut), `bounding_box`.

**Champs** [3] :

- zone et dates : `date_ech`, `date_dif`, `code_zone`, `lib_zone`, `type_zone` ;
- indice : `code_qual`, `lib_qual`, `coul_qual`, `pollen_resp` (taxons responsables),
  `alerte` ;
- sous-indices : `code_aul`, `code_boul`, `code_oliv`, `code_gram`, `code_arm`, `code_ambr` ;
- concentrations en grains/m³ : `conc_aul`, `conc_boul`, `conc_oliv`, `conc_gram`,
  `conc_arm`, `conc_ambr`.

**Profondeur.**

- Notice : « l'année en cours jusqu'à J+2 », ailleurs « 1 an glissant » [3].
- WFS public `ind_pol:ind_pol` : J à J+2 seulement (vérifié : 104 418 lignes, soit 3 jours
  pour environ 34 800 communes).

## Thème 4 : inventaires des émissions et consommations d'énergie

Les deux thèmes sont **un seul flux** : la route émissions porte aussi les champs `conso_*`.
Il n'existe pas de route « consommations » séparée [1].

**Route API v2** : `GET /api/v2/data/inventaires/emissions` [1]. Paramètres :

- `annee` : 2010, 2018 ou 2022 ;
- `echelle` : `region` (défaut), `epci` ou `departement` ;
- `code_zone` : EPCI ou département uniquement ;
- `aasqa` ;
- `secteur` (`code_pcaet`) : 5 Agriculture, 219 Industrie + branche énergie + déchets,
  34 Résidentiel-Tertiaire, 6 Transport routier, 7 Autres transports ; `All` pour le total ;
- `bounding_box`.

**Granularité.** Région, département, EPCI. **Pas de commune** dans Atmo Data. La notice
renvoie vers les AASQA régionales pour un détail plus fin [3].

**Méthode.** Inventaires territoriaux conformes au guide **PCIT** (2e édition, juin 2018 :
Citepa, Atmo France, INERIS), dans le cadre de l'arrêté SNIEBA, format de rapportage PCAET
(arrêté du 4 août 2016) [3]. La méthode est propre à chaque AASQA. Le champ
`versioning_inventaire` vaut par exemple `M2024`, `V2025`, `icare3.2`, `BASEMIS_V8`,
`ISEA_V6`, `TRACE v5`, `ATMO_IRS_V8.1` (vérifié). Les GES couvrent CO2, CH4 et N2O, sans les
gaz fluorés, avec les PRG à 100 ans du 5e rapport du GIEC. Ils incluent le scope 1 et le
scope 2, **sauf l'Occitanie à l'échelle EPCI** (scope 1 seul) [3].

**Polluants.** La notice cite NOx, PM10, PM2.5 et GES [3]. Le flux réel contient aussi
**NH3, SO2 et COVNM** (vérifié sur `emissions:emissions_epci`).

**Unités.**

- Notice : NOx, PM10 et PM2.5 en tonnes/an [3].
- GES : la notice se contredit (« kteqCO₂/an » dans le résumé, « unité de base tonne » dans
  le tableau des champs) [3]. Les ordres de grandeur penchent pour la **tonne éq. CO2**
  (vérifié) : 12,8 Mt pour la Métropole du Grand Paris, soit 1,8 t/hab ; 5,0 Mt pour la
  Métropole de Lyon.
- Consommations : **unité non documentée**. L'hypothèse du **GWh** est cohérente
  (résidentiel-tertiaire de la Métropole du Grand Paris : 65 748, soit environ 9,3 MWh/hab).
  **Non vérifié.**

**Champs consommations** : `conso` (total), `conso_elec`, `conso_gn` (gaz naturel),
`conso_pp` (produits pétroliers), `conso_cms` (combustibles minéraux solides),
`conso_bois`, `conso_chaleur`, `conso_autres_enr`, `conso_autres` (vérifié). Les
définitions exactes ne sont pas documentées dans la notice : **non vérifié**.

**Autres champs** : `code`, `name`, `code_pcaet`, `annee`, `population`, `superficie`,
`aasqa`, `source`, `versioning_inventaire`, `date_maj`.

**Millésimes et couverture.** La notice d'avril 2025 parle de la seule année de référence
2018 (2015 pour la Guyane) [3]. Le flux contient 2010, 2018 et 2022 (vérifié) :

| Année | EPCI avec total `All` | EPCI détaillés par secteur |
|---|---|---|
| 2010 | 1 220 | 1 062 |
| 2018 | 1 250 | 1 092 |
| 2022 | 1 232 | 1 074 |

- **2022 : aucune donnée outre-mer.** Guadeloupe et Réunion n'ont que 2018 ; Martinique et
  Guyane, 2010 et 2018.
- La Corse n'a pas 2010.
- **Mayotte n'a aucune donnée** ; la notice dit aussi « données non communiquées » pour la
  Réunion, alors que le flux en contient.
- La notice affirme que les EPCI n'ont que le total `All` [3]. Le flux contient pourtant les
  cinq secteurs pour environ 1 070 EPCI par millésime (vérifié). La notice est en retard
  sur les données.
- La somme des secteurs égale le total à 2 % près pour 2 893 couples (EPCI, année) ; elle
  s'en écarte pour 32 (vérifié).

**Découpage** : ADMIN-EXPRESS de mars 2023 [3]. Une commune qui a changé d'EPCI depuis doit
être rattachée par l'EPCI de 2023, pas par l'EPCI courant.

## API v2 et WFS public sans compte

Le WFS public est le flux que le projet utilise déjà ; la carte `https://map.atmo-france.org/flux`
y renvoie [3]. Couches listées par `GetCapabilities` [5] :

- `alrt:alrt` (historique des épisodes), `alrt:alrt3j` et `alrt:national_alrt3j` (J-1 à J+1) ;
- `emissions:emissions_regions`, `emissions:emissions_dpt`, `emissions:emissions_epci` ;
- `ind:ind_atmo_2021` (utilisée), `ind:ind_atmo`, `ind:ind_atmo_partition_week`,
  `ind:ind_atmo_tile` et `ind:ind_atmo_tile_2` ;
- `ind_pol:ind_pol`, `ind_pol:ind_national_pol` et leurs variantes `_tile`.

| Thème | WFS public (sans compte) | API v2 (jeton) |
|---|---|---|
| Indice ATMO | J à J+2 (`ind:ind_atmo_2021`) | idem, plus l'historique : un an d'après la notice, trois jours d'après la spec [1][3] |
| Épisodes 3 jours | `alrt:alrt3j` | `/episodes/3jours` |
| Historique des épisodes | `alrt:alrt`, de 2008 à 2026, inégal | `/episodes/historique` (« l'année passée ») |
| Émissions et consommations | les 3 couches, millésimes 2010, 2018 et 2022, secteurs | idem, filtres en paramètres |
| Pollen | J à J+2 (`ind_pol:ind_pol`) | idem, plus l'historique (« 1 an glissant ») [3] |

Notes :

- `ind:ind_atmo_partition_week` renvoie 0 ligne pour Valence ; `ind:ind_atmo` est tombée en
  504 (délai dépassé) à deux reprises. Leur contenu n'a pas été examiné.
- Les CGU couvrent « API, carte… » sous la même licence ODbL [4]. Le WFS ne déclare aucune
  contrainte d'accès (`AccessConstraints NONE`, `Fees NONE`) [5].
- **Conclusion : pour les épisodes, les émissions et les consommations, le WFS public suffit.
  Il n'y a pas de secret à gérer et le client `HttpClient` et le filtre CQL existent déjà.
  L'API n'apporte de vraie valeur que pour l'historique de l'indice ATMO et du pollen, qui
  reste à confirmer avec le jeton.**

## Pertinence pour le rapport immobilier

**Données stables**, utiles à un acheteur, avec un cache long possible :

- **Émissions par EPCI et par secteur** (2010, 2018, 2022) : par habitant et par km², et
  évolution entre 2018 et 2022.
- **Consommations d'énergie par EPCI et par énergie** : part du bois, du fioul, du gaz, de
  l'électricité dans le résidentiel-tertiaire.

Ce sont des indicateurs du territoire, pas de l'adresse.

**Données semi-stables** :

- Historique des épisodes par département ou bassin d'air : nombre de jours d'information
  ou d'alerte sur 12 mois, polluant dominant (ozone l'été, particules l'hiver). C'est
  utile, mais la série n'est fiable que depuis 2025 pour la plupart des AASQA. Il faut
  afficher la période réellement couverte.
- Si l'API donne un an d'indices ATMO par commune : nombre de jours « Dégradé » ou pire sur
  12 mois glissants. Avec la réserve de la notice : ce n'est pas une mesure d'exposition
  annuelle [3].

**Données éphémères** : indice ATMO du jour (déjà affiché) et pollen du jour. Leur valeur
pour un achat est faible. Le pollen pourrait au mieux servir à un message saisonnier
(« zone à ambroisie »), mais **non vérifié** : aucune statistique annuelle de pollen n'est
publiée par Atmo Data.

**Moyennes annuelles NO2 ou PM2.5 par commune** : **aucune route ni couche Atmo Data ne les
fournit** (spec v2 et `GetCapabilities` vérifiés). Les AASQA en publient parfois au niveau
régional, par exemple le jeu « Indicateurs Air et Santé » d'Atmo Auvergne-Rhône-Alpes
repéré sur data.gouv.fr, non examiné. Une autre source nationale ouverte, hors Atmo, reste
à chercher dans une recherche séparée : **non vérifié**.

**Contraintes du projet** :

- Tout nouveau champ dans `qualite_air` ou dans un nouveau bloc impose d'incrémenter
  `report_version` (`.claude/rules/sources.md`).
- Les inventaires sont des données datées (millésime). Le rapport doit afficher l'année et
  `versioning_inventaire`, sur le modèle de `.claude/rules/millesimes.md`.
- Attribution ODbL « Atmo France / AASQA », avec le nom de l'AASQA, dans
  `legalContent.ts`.
- Le jeton, s'il est utilisé, est un secret serveur. Il ne doit jamais être en `VITE_`.
- Le renouvellement toutes les 24 h doit passer par `app/core/http.py`.

## Vérifications complémentaires (2026-10-20)

- **Connexion à l'API** (avec le compte du projet) : `/api/login` renvoie un objet à une
  seule clé, `token`.
- **Historique de l'API** : `date=2026-10-20` et `date_historique=2025-10-20` sur Valence
  (`26362`) renvoient **un seul jour** pour `/indices/atmo` comme pour `/indices/pollens`.
  L'historique d'un an annoncé par la notice n'est pas servi : l'API n'apporte rien de plus
  que le WFS public. Décision : on ne l'utilise pas.
- **Géométrie de `alrt:alrt`** (`the_geom`, EPSG:3857) : de vrais polygones pour les bassins
  d'air d'Auvergne-Rhône-Alpes. Un filtre `INTERSECTS(the_geom, SRID=3857;POINT(x y))` sur
  Lyon renvoie bien le bassin `2003` « Bassin Lyon Nord-Isère ». Les départements et
  l'Île-de-France n'ont qu'un **point** : le filtre spatial ne marche pas pour eux, il faut
  passer par le code de département.
- **Pas de champ `aasqa`** dans `alrt:alrt` (`DescribeFeatureType`). Seuls champs :
  `date_maj`, `lib_pol`, `lib_zone`, `etat`, `date_ech`, `date_dif`, `code_zone`, `code_pol`,
  `the_geom`. La collision `code_zone = "11"` (Aude ou Île-de-France) se lève donc par
  `lib_zone` (`AUDE`, `ILE-DE-FRANCE`), pas par l'AASQA comme le suggère le piège 1.
- **Méthode identique d'un millésime à l'autre** au sein d'une région : pour la Métropole de
  Lyon (`200046977`), les lignes 2010, 2018 et 2022 portent toutes `versioning_inventaire =
  M2024` et la même `date_maj`. Les millésimes anciens sont recalculés avec la méthode
  courante, ce qui rend l'évolution 2018 → 2022 comparable dans un EPCI. Une version par
  région, en revanche (13 versions pour 13 régions en 2022).
- **GES en tonnes éq. CO2**, confirmé : la somme de `emissions:emissions_regions` (total
  `All`) donne 376,4 Mt pour 2022, soit 5,73 t/hab. Les 13 régions de 2022 sont exactement la
  métropole, Corse comprise. On a 17 régions pour 2018 (métropole et quatre DROM, sans
  Mayotte) et 14 pour 2010. Le repère « France métropolitaine » se calcule donc sur les 13
  régions métropolitaines, pour chaque millésime.
- Dans `alrt:alrt`, `code_pol` est le code court (`5` PM10, `7` O3), pas le code UE à quatre
  chiffres de la spec.

## Pièges

1. **Collision de codes dans les épisodes** : `code_zone = "11"` désigne à la fois l'Aude et
   l'Île-de-France (vérifié). Les Ardennes sont codées `"8"` et non `"08"` (vérifié). Il faut
   filtrer sur le couple (`aasqa`, `code_zone`), et non sur `code_zone` seul. Pour
   l'Île-de-France, chercher la zone région `11` avec `aasqa = 11` dans `national_alrt3j`.
2. **Bassins d'air en Auvergne-Rhône-Alpes** (codes `2000` à `2020`) : il faut une table
   commune vers bassin, que ni la spec ni la notice ne donnent. **Non vérifié** : où
   l'obtenir. Il y a peut-être des géométries dans le flux, puisque `geom` est facultatif.
3. **Libellés non normalisés.**
   - `lib_pol` prend 14 formes : `O3`, `Ozone`, `OZONE`, `PM10`, `Particules fines PM10`…
     `code_pol` est plus fiable : 1 SO2, 5 PM10, 6001 PM2.5, 7 O3, 8 NO2. On trouve aussi
     les codes isolés `08` et `24`.
   - `type_zone` existe en `EPCI`, `epci`, `COMMUNE`, `Commune`.
   - `source` mélange `Atmo HDF` et `Atmo Hauts-de-France`.
   - En Corse, des libellés historiques sont inversés entre `2A` et `2B`.
   (Tout vérifié.)
4. **Valeur « événement »** : 7 d'après la spec v2 et la notice [1][3], 8 d'après la FAQ de
   2023 [2]. Le code actuel exclut tout ce qui sort de 1 à 6, ce qui couvre les deux cas.
5. **Arrondissements.**
   - Indice ATMO : `75056` (Paris), `69123` et `69381` (Lyon), `13055` et `13201`–`13216`
     (Marseille) sont présents. Le 1er arrondissement de Lyon a `lib_zone` vide. Les
     arrondissements de Paris sont absents (vérifié).
   - Pollen : commune entière seulement (vérifié).
   - Émissions : EPCI seulement (Métropole du Grand Paris `200054781`, Métropole de Lyon
     `200046977`, Aix-Marseille-Provence `200054807`).
6. **Communes fusionnées** : millésime du COG utilisé pour `code_zone` des indices **non
   vérifié**. Les émissions suivent ADMIN-EXPRESS de mars 2023 [3]. Prévoir le repli vers
   l'EPCI, comme aujourd'hui.
7. **Indice 2021** : la couche `ind_atmo_2021` suit l'arrêté de 2020 (6 classes avec PM2.5).
   L'ancien indice (avant 2021, autre échelle) n'est pas comparable [9]. Ne pas mélanger avec
   la couche `ind:ind_atmo`.
8. **Ruptures de série** : pollen au 1er avril 2025 (RNSA vers AASQA) [11] ; épisodes
   alimentés massivement seulement depuis 2025 ; inventaires recalculés à chaque version de
   méthode. Un millésime 2018 d'aujourd'hui n'est pas celui de 2023, et comparer 2018 et
   2022 n'a de sens qu'à méthode identique, ce que le champ `versioning_inventaire` laisse
   supposer pour un même lot.
9. **Occitanie** : indice ATMO à l'EPCI seulement ; GES EPCI sans le scope 2 [3].
10. **Outre-mer** : pas de pollen ; pas d'émissions 2022 ; rien pour Mayotte dans les
    émissions.
11. **Exemples de la spec en EPSG:3857** (`crs` des fichiers `/exemple_*.json`) [1]. Le WFS
    renvoie ce qu'on lui demande. Les géométries sont inutiles ici : utiliser
    `propertyName` et `with_geom=false`.

## Questions ouvertes (à trancher avec le jeton ou auprès de data@atmo-france.org)

1. Profondeur réelle de `/api/v2/data/indices/atmo` avec `date_historique` : un an (notice)
   ou trois jours (spec) ? Même question pour `/indices/pollens`.
2. Format exact de la réponse de `/api/login` (champ du jeton, expiration) et durée réelle
   de validité (24 h ou 1 h).
3. Existence de quotas ou d'une limite de débit.
4. L'ancienne route v1 `/api/data/{id}/{filtre}` (ids 112, 113, 114) est-elle encore servie ?
5. Unité des champs `conso*` (GWh supposé) et définition de chaque énergie ; unité définitive
   des GES (tonne éq. CO2 supposée).
6. Table de correspondance commune vers bassin d'air en Auvergne-Rhône-Alpes.
7. Millésime du COG des `code_zone` de l'indice ATMO et du pollen.
8. Position d'Atmo France sur un usage commercial explicite : l'ODbL le permet, mais les CGU
   n'en disent rien.
9. Calendrier du prochain millésime d'inventaire après 2022.

## Sources (consultées le 2026-10-20)

1. Spec OpenAPI v2 d'Atmo Data, intégrée à la page Swagger :
   https://admindata.atmo-france.org/api/doc/v2. Exemples de réponse :
   https://admindata.atmo-france.org/exemple_indices.json, `/exemple_episodes.json`,
   `/exemple_emissions.json`, `/exemple_pollens.json`. Spec v1 :
   https://admindata.atmo-france.org/api/doc
2. FAQ API Atmo Data, version du 12 avril 2023 :
   https://www.atmo-france.org/sites/federation/files/medias/documents/2023-04/FAQ_API_Atmo_Data_20230412.pdf
   (une version du 10 octobre 2023 existe mais n'a pas pu être lue :
   https://atmo-France.org/sites/federation/files/medias/documents/2023-10/FAQ_API_Atmo_Data_20231010_0.pdf)
3. Notice technique Atmo Data, version du 1er avril 2025 :
   https://www.atmo-france.org/sites/federation/files/medias/documents/2025-04/notice_Atmo_Data_1eravril2025.pdf
4. Conditions générales d'utilisation d'Atmo France (version du 2 avril 2025) :
   https://www.atmo-france.org/article/conditions-generales-dutilisation
5. WFS public, GetCapabilities et requêtes GetFeature :
   https://data.atmo-france.org/geoserver/ows?service=WFS&version=2.0.0&request=GetCapabilities
6. Formulaire d'inscription : https://admindata.atmo-france.org/inscription-api
7. data.gouv.fr, jeu « Atmo Data » :
   https://www.data.gouv.fr/datasets/atmo-data-la-plateforme-nationale-des-flux-open-data-des-associations-agreees-de-surveillance-de-la-qualite-de-lair
8. data.gouv.fr, jeu « Données émissions… région et EPCI » :
   https://www.data.gouv.fr/datasets/donnees-emissions-a-lechelle-de-la-region-et-de-letablissement-public-de-cooperation-intercommunale-epci
9. Arrêté du 10 juillet 2020 relatif à l'indice de la qualité de l'air ambiant :
   https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000042164835
10. Arrêté du 7 avril 2016 relatif au déclenchement des procédures préfectorales en cas
    d'épisodes de pollution de l'air ambiant :
    https://www.legifrance.gouv.fr/loda/id/JORFTEXT000032376671/ (lu par extrait de
    recherche seulement)
11. data.gouv.fr, jeu « Indices et bulletin pollinique » (AtmoSud) :
    https://www.data.gouv.fr/datasets/indices-et-bulletin-pollinique
12. Guide de calcul du nouvel indice ATMO (décembre 2020), cité par la spec, téléchargé mais
    pas exploité ici :
    https://www.atmo-france.org/sites/federation/files/medias/documents/2022-04/guide_calcul_nouvel_indice_ATMO_VF_version14decembre2020.pdf
