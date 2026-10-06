/** Contrats de l'API d'audit (miroir de backend/app/schemas/audit.py). */

export type SourceStatus = 'ok' | 'partial' | 'empty' | 'error' | 'timeout' | 'unavailable'

export interface SourceResult<T = unknown> {
  status: SourceStatus
  data: T | null
  missing: string[]
  error: string | null
  duration_ms: number
  /** Date d'interrogation de la source (chaque source a sa durée de validité en cache). */
  fetched_at?: string | null
}

export interface AuditLocation {
  lat: number
  lon: number
  label: string
  citycode: string
  postcode: string | null
  city: string | null
  region?: string | null
  ban_id: string
  /** Identifiant BAN de l'adresse la plus proche, résolu par le serveur. */
  adresse_id?: string | null
  /** Présent quand l'audit porte sur une voie entière ; `points` : [lon, lat] de ses numéros. */
  rue?: { id: string; nom: string; nb_numeros: number; longueur_m: number; points: [number, number][] } | null
}

/** Constat de la synthèse ; en aperçu gratuit, `titre` et `detail` valent "***LOCKED***". */
export interface Finding {
  theme: string
  titre: string
  detail: string
}

export interface ReportSynthesis {
  alertes: Finding[]
  points_forts: Finding[]
}

export interface ReportMeta {
  generated_at: string
  cached: boolean
  is_partial: boolean
  /** "teaser" : le serveur a remplacé les valeurs réservées par "***LOCKED***". */
  access?: 'full' | 'teaser'
  /** Sources n'ayant pas (entièrement) répondu ; absent des rapports mis en cache avant la v2. */
  failed_sources?: string[]
  report_version: number
  duration_ms: number
  /** Alertes et points forts les plus marquants ; absent des rapports antérieurs à la v7. */
  synthese?: ReportSynthesis | null
}

/** Adresse choisie dans l'autocomplétion BAN. */
export interface AddressSuggestion {
  id: string
  label: string
  context: string
  lat: number
  lon: number
  /** Vrai pour une voie entière : l'audit agrège alors le long de la rue. */
  street?: boolean
}

// --- Données par source. Tout champ peut manquer si la source n'a répondu que partiellement.

export interface GeorisquesData {
  risques?: string[]
  inondation?: { concerne: boolean; atlas_zones_inondables: string[] }
  /** `variable` : en mode « rue », l'exposition change le long de la voie (la plus forte est donnée). */
  argiles?: { code: string | null; exposition: string | null; variable?: boolean }
  sismicite?: { code: string | null; zone: string | null } | null
  radon?: { classe_potentiel: string | null } | null
  seveso?: {
    rayon_m: number
    sites: { nom: string | null; statut: string; commune: string | null; distance_m: number | null }[]
    installations_classees_total: number | null
    liste_tronquee: boolean
  }
  catastrophes_naturelles?: { nb_arretes: number | null }
  /** Recommandation par risque (clés : argiles, radon, inondation, sismicite), fournie par le serveur. */
  recommandations?: Record<string, string>
}

export interface CadastreData {
  identifiant: string | null
  section: string | null
  numero: string | null
  contenance_m2: number | null
  commune: string | null
}

export interface UrbanismeData {
  zones: {
    libelle: string | null
    libelle_long: string | null
    type_zone: string | null
    document: string | null
    date_validation: string | null
    reglement: string | null
  }[]
}

export interface DvfSale {
  date: string
  prix: number
  surface_m2: number
  prix_m2: number
  type: string
  pieces: number | null
  /** Numéro dans la voie. */
  numero?: number | null
  distance_m: number
}

export interface DvfData {
  /** « rue » : ventes de la voie auditée ; « rayon » (ou absent) : ventes autour du point. */
  perimetre?: 'rue' | 'rayon'
  rue?: string
  /** Absent en mode « rue ». */
  rayon_m?: number
  /** Repère du mode « rue » : ventes de tout le secteur traversé. */
  comparaison?: { perimetre: string; nb_ventes: number; prix_m2_median: number; ecart_pct: number }
  nb_ventes: number
  prix_m2_median: number
  dispersion: { min: number; q1: number; q3: number; max: number }
  par_type: Record<string, { nb_ventes: number; prix_m2_median: number }>
  historique: { annee: number; nb_ventes: number; prix_m2_median: number }[]
  dernieres_ventes: DvfSale[]
  sections_interrogees: number
}

export interface DpeData {
  perimetre?: 'rue' | 'rayon'
  rue?: string
  /** Mode « rue » : synthèse par numéro de la voie. */
  par_numero?: { numero: string; nb_dpe: number; etiquette_dominante: string | null; annee_construction: number | null }[]
  /** Absent en mode « rue ». */
  rayon_m?: number
  /** Distance du diagnostic analysé le plus lointain : l'échantillon est pris du plus proche au plus loin. */
  rayon_effectif_m?: number | null
  nb_dpe_total: number | null
  nb_dpe_analyses: number
  repartition_dpe: Record<string, number>
  repartition_ges: Record<string, number>
  etiquette_dominante: string | null
  analyse?: { part_efg_pct: number | null; levier_negociation: boolean; message: string | null }
}

export interface PointOfInterest {
  type: string
  nom: string | null
  distance_m: number
  marche_min: number
}

export interface ProximiteData {
  rayon_m: number
  methode_temps?: 'vol_d_oiseau' | 'itineraire_pieton'
  categories: Record<string, { nb: number; plus_proche: PointOfInterest | null }>
}

export interface QualiteAirData {
  /** Indice ATMO : 1 (bon) à 6 (extrêmement mauvais). */
  indice: number
  qualificatif: string
  date: string
  zone: { code: string; nom: string | null; type: string }
  sous_indices: Record<'pm2_5' | 'pm10' | 'no2' | 'o3' | 'so2', number | null>
  polluants_dominants: string[]
  demain: { indice: number; qualificatif: string } | null
  producteur: string | null
  origine: string
}

export interface EnsoleillementData {
  altitude_m: number
  score: { annuel: number; solstice_hiver: number }
  masque_relief_deg: Record<string, number>
  synthese?: string
  methode: string
}

export interface LoyersData {
  type_bien: string
  loyer_m2_charges_comprises: number | null
  intervalle_prediction: [number | null, number | null]
  nb_observations: number | null
  niveau_prediction: string | null
  millesime: number
}

export interface DelinquanceData {
  annee: number
  indicateurs: {
    indicateur: string
    unite_de_compte: string
    est_diffuse: boolean
    nombre: number | null
    taux_pour_mille: number | null
    /** Taux pour 1 000 hab. du département, de la France et de la commune l'année précédente. */
    reperes?: { departement: number | null; national: number | null; annee_precedente: number | null }
  }[]
}

export interface TaxeFonciereData {
  annee: number
  libelle_commune: string
  taux_tfb_commune: number
  taux_tfb_epci: number
  taux_tfb_total: number
  taux_teom: number | null
  /** Taux global médian des communes du département et de France. */
  reperes?: { mediane_departement: number | null; mediane_nationale: number | null }
}

export interface EcolesData {
  rayon_m: number
  ips_moyen: number | null
  /** IPS moyen par niveau, avec les moyennes du département et de France. */
  par_type?: Partial<
    Record<
      'ecole' | 'college' | 'lycee',
      { nb: number; ips_moyen: number; moyenne_departement: number | null; moyenne_nationale: number | null }
    >
  >
  etablissements: {
    uai: string
    nom: string
    type_etablissement: 'ecole' | 'college' | 'lycee'
    secteur: 'public' | 'prive'
    ips: number
    distance_m: number
  }[]
}

export interface PermisData {
  rayon_m: number
  nb_permis: number
  risque_vis_a_vis: boolean
  nb_projets_a_risque: number
  permis: {
    num_permis: string
    etat: string
    date_autorisation: string
    nature_projet: string | null
    destination: string | null
    nb_logements: number | null
    nb_niveaux: number | null
    adresse: string | null
    precision_geocodage: 'numero' | 'voie'
    distance_m: number
  }[]
}

export interface MarcheLocatifData {
  occupation?: {
    iris: { code: string; nom: string | null }
    annee: number
    logements: number
    part_proprietaires_pct: number | null
    part_locataires_pct: number | null
    part_locataires_hlm_pct: number | null
    part_vacants_pct: number | null
    part_residences_secondaires_pct: number | null
  } | null
  encadrement_loyers?: { statut: 'oui' | 'partiel' | 'non'; territoire: string | null; verifie_le: string }
  permis_de_louer: { statut: string }
}

export interface ConnectiviteData {
  niveau: string
  date_donnees: string
  nb_locaux: number
  part_fibre_pct: number | null
  part_cable_pct: number | null
  part_4g_fixe_pct: number | null
}

export interface CoproprieteData {
  charges_m2_an: number
  niveau: 'ville' | 'region'
  territoire: string
  millesime: number
  origine: string
}

export interface ReseauMobileData {
  rayon_m: number
  nb_sites: number
  operateurs: { nom: string; generations: string[]; nb_sites: number; site_le_plus_proche_m: number }[]
  operateurs_5g: string[]
  liste_tronquee: boolean
}

export interface BruitData {
  indice: string
  /** Borne basse de la classe la plus forte ; null si le point est hors des zones cartographiées. */
  niveau_max_db: number | null
  /** Mode « rue » : part des numéros de la voie situés en zone de bruit. */
  part_rue_pct?: number
  sources: { infrastructure: 'route' | 'fer' | 'air' | 'industrie'; db_min: number; db_max: number | null }[]
  /** Types d'infrastructure dont la carte existe sur ce secteur ; absent des rapports antérieurs. */
  infrastructures_couvertes?: BruitData['sources'][number]['infrastructure'][]
  message: string
}

/** Nom de source -> forme de ses données. */
export interface SourceDataMap {
  georisques: GeorisquesData
  cadastre: CadastreData
  urbanisme: UrbanismeData
  dvf: DvfData
  dpe: DpeData
  proximite: ProximiteData
  qualite_air: QualiteAirData
  ensoleillement: EnsoleillementData
  loyers: LoyersData
  delinquance: DelinquanceData
  taxe_fonciere: TaxeFonciereData
  ecoles: EcolesData
  permis_construire: PermisData
  marche_locatif: MarcheLocatifData
  connectivite: ConnectiviteData
  copropriete: CoproprieteData
  reseau_mobile: ReseauMobileData
  bruit: BruitData
}

export type SourceName = keyof SourceDataMap

export type SourceResults = { [K in SourceName]?: SourceResult<SourceDataMap[K]> }
