import type { SourceName, SourceStatus } from '../types/audit'

interface SourceInfo {
  title: string
  /** Affiché quand la source répond mais n'a rien pour cette adresse. */
  emptyText: string
}

export const SOURCE_INFO: Record<SourceName, SourceInfo> = {
  dvf: {
    title: 'Prix de vente (DVF)',
    emptyText: 'Aucune vente de logement enregistrée dans un rayon de 300 m.',
  },
  loyers: { title: 'Loyers', emptyText: 'Pas d’indicateur de loyer pour cette commune.' },
  taxe_fonciere: { title: 'Taxe foncière', emptyText: 'Taux non disponible pour cette commune.' },
  georisques: { title: 'Risques naturels et technologiques', emptyText: 'Aucun risque recensé.' },
  cadastre: {
    title: 'Parcelle cadastrale',
    emptyText: 'Le point se situe sur le domaine public (voirie) : aucune parcelle.',
  },
  urbanisme: {
    title: 'Urbanisme (PLU)',
    emptyText: 'Aucun document d’urbanisme publié pour ce point.',
  },
  permis_construire: {
    title: 'Permis de construire à proximité',
    emptyText: 'Aucun permis récent dans un rayon de 150 m.',
  },
  dpe: {
    title: 'Performance énergétique (DPE)',
    emptyText: 'Aucun diagnostic enregistré dans un rayon de 150 m.',
  },
  batiment: {
    title: 'Le bâtiment',
    emptyText: 'Adresse non rattachée à un bâtiment dans la base nationale des bâtiments.',
  },
  qualite_air: {
    title: 'Qualité de l’air',
    emptyText: 'Indice ATMO non publié pour cette commune aujourd’hui.',
  },
  ensoleillement: { title: 'Ensoleillement', emptyText: 'Calcul impossible pour ce point.' },
  proximite: {
    title: 'Transports et commerces à pied',
    emptyText: 'Aucun équipement trouvé à proximité.',
  },
  ecoles: {
    title: 'Établissements scolaires',
    emptyText: 'Aucun établissement dans un rayon de 1,5 km.',
  },
  marche_locatif: {
    title: 'Marché locatif du quartier',
    emptyText: 'Pas de donnée de recensement pour ce quartier.',
  },
  quartier: {
    title: 'Profil du quartier',
    emptyText: 'Pas de donnée de l’INSEE pour ce quartier.',
  },
  connectivite: {
    title: 'Internet fixe',
    emptyText: 'Pas de statistique d’éligibilité pour cette commune.',
  },
  copropriete: {
    title: 'Charges de copropriété',
    emptyText: 'Pas de moyenne disponible pour ce territoire.',
  },
  reseau_mobile: {
    title: 'Réseau mobile',
    emptyText: 'Aucune antenne-relais active à moins de 1 km.',
  },
  bruit: {
    title: 'Bruit des infrastructures',
    emptyText: 'Cartes de bruit non intégrées à notre base pour ce secteur : consultez celles de la préfecture.',
  },
  delinquance: {
    title: 'Délinquance enregistrée',
    emptyText: 'Pas de statistique pour cette commune.',
  },
}

export const FAILURE_LABELS: Partial<Record<SourceStatus, string>> = {
  error: 'Indisponible',
  timeout: 'Délai dépassé',
  unavailable: 'Suspendue',
}

export function isFailure(status: SourceStatus): boolean {
  return status in FAILURE_LABELS
}

/** Libellés partagés par l'écran et le PDF. */
export const POI_CATEGORY_LABELS: Record<string, string> = {
  transports: 'Transports',
  commerces: 'Commerces alimentaires',
  sante: 'Santé',
  education: 'Écoles et crèches',
  espaces_verts: 'Parcs',
}

/** Catégories de proximité dans leur ordre d'affichage (l'ordre des clés reçues n'est pas garanti). */
export function orderedCategories<T>(categories: Record<string, T>): [string, T][] {
  const known = Object.keys(POI_CATEGORY_LABELS).filter((key) => key in categories)
  const others = Object.keys(categories).filter((key) => !(key in POI_CATEGORY_LABELS))
  return [...known, ...others].map((key) => [key, categories[key] as T])
}

export const SCHOOL_KIND_LABELS = { ecole: 'École', college: 'Collège', lycee: 'Lycée' } as const

export const DATA_SOURCES =
  'BAN, DVF, Géorisques, IGN, ADEME, INSEE, ANCT, SSMSI, DGFiP, Éducation nationale, SDES, ARCEP, ANFR, ' +
  'directions départementales des territoires (bruit), Atmo France et associations agréées de surveillance de la qualité de l’air, OpenStreetMap'
