import type {
  BatimentData,
  BruitData,
  ReportSynthesis,
  ConnectiviteData,
  DelinquanceData,
  DvfData,
  EcolesData,
  GeorisquesData,
  MarcheLocatifData,
  ReseauMobileData,
  SourceResults,
  TaxeFonciereData,
  UrbanismeData,
} from '../types/audit'
import {
  capitalize,
  formatDate,
  formatDecimal,
  formatDistance,
  formatEuros,
  formatInteger,
  formatPercent,
  formatPricePerM2,
} from './format'
import { inPreventionPlan, riskIndicators } from './insights'
import { yieldLines } from './yield'
import { isFailure, orderedCategories, POI_CATEGORY_LABELS, SCHOOL_KIND_LABELS } from './sources'

export interface ReportSection {
  title: string
  /** Lignes « libellé / valeur ». */
  rows: [string, string][]
  /** Tableau détaillé facultatif. */
  table?: { head: string[]; body: string[][] }
}

type Rows = [string, string][]

function salesTable(dvf: DvfData): ReportSection['table'] {
  return {
    head: ['Date', 'Bien', 'Prix', '€/m²', dvf.perimetre === 'rue' ? 'N°' : 'Distance'],
    body: dvf.dernieres_ventes.map((sale) => [
      formatDate(sale.date),
      [capitalize(sale.type), `${formatInteger(sale.surface_m2)} m²`, sale.pieces ? `${sale.pieces} p.` : '']
        .filter(Boolean)
        .join(', '),
      formatEuros(sale.prix),
      formatInteger(sale.prix_m2),
      dvf.perimetre === 'rue' ? String(sale.numero ?? '-') : formatDistance(sale.distance_m),
    ]),
  }
}

/** Médiane des 24 derniers mois, avec son évolution quand elle est connue. */
function recentRows(dvf: DvfData): Rows {
  const recent = dvf.recent
  if (!recent) return []
  let trend = ''
  if (recent.tendance_pct !== null) {
    trend = `, ${recent.tendance_pct > 0 ? '+' : ''}${formatDecimal(recent.tendance_pct)} % en deux ans`
  } else if (recent.tendance) {
    trend = `, ${recent.tendance} sur deux ans`
  }
  return [
    [
      `Prix médian au m², ${recent.mois} derniers mois`,
      `${formatPricePerM2(recent.prix_m2_median)} (${formatInteger(recent.nb_ventes)} ventes${trend})`,
    ],
  ]
}

function priceRows(dvf: DvfData | null | undefined): Rows {
  if (!dvf) return []
  const street = dvf.perimetre === 'rue'
  const comparison: Rows = dvf.comparaison
    ? [
        [
          'Écart avec le quartier',
          `${dvf.comparaison.ecart_pct > 0 ? '+' : ''}${formatDecimal(dvf.comparaison.ecart_pct)} % (${formatPricePerM2(dvf.comparaison.prix_m2_median)} sur ${formatInteger(dvf.comparaison.nb_ventes)} ventes)`,
        ],
      ]
    : []
  return [
    ...recentRows(dvf),
    [street ? 'Prix médian au m² (ventes de la rue)' : `Prix médian au m² (${dvf.rayon_m ?? 300} m)`, formatPricePerM2(dvf.prix_m2_median)],
    ...comparison,
    ['Ventes analysées', formatInteger(dvf.nb_ventes)],
    [
      'Moitié des ventes comprise entre',
      `${formatPricePerM2(dvf.dispersion.q1)} et ${formatPricePerM2(dvf.dispersion.q3)}`,
    ],
    ...Object.entries(dvf.par_type).map(
      ([kind, stats]): [string, string] => [`Prix médian, ${kind}`, formatPricePerM2(stats.prix_m2_median)],
    ),
  ]
}

function taxRows(tax: TaxeFonciereData | null | undefined): Rows {
  if (!tax) return []
  return [
    [
      `Taxe foncière ${tax.annee}, taux global`,
      tax.reperes?.mediane_departement
        ? `${formatPercent(tax.taux_tfb_total, 2)} (commune médiane du département : ${formatPercent(tax.reperes.mediane_departement, 2)})`
        : formatPercent(tax.taux_tfb_total, 2),
    ],
    ['Taxe d’ordures ménagères', formatPercent(tax.taux_teom, 2)],
  ]
}

function market(sources: SourceResults): ReportSection {
  const dvf = sources.dvf?.data
  const rent = sources.loyers?.data
  const rentRows: Rows = rent
    ? [['Loyer d’annonce, appartement', `${formatDecimal(rent.loyer_m2_charges_comprises)} €/m²`]]
    : []
  // Une ligne par type de bien : loyer de ce type rapporté au prix des biens du même type.
  const yieldRows: Rows = yieldLines(rent, dvf).map((line) => [
    `Rendement locatif brut, ${line.label.toLowerCase()} (avant taxe foncière et charges)`,
    `${formatPercent(line.gross)} — ${formatDecimal(line.rentPerM2)} €/m² pour ${formatPricePerM2(line.pricePerM2)}`,
  ])
  const condo = sources.copropriete?.data
  const condoRows: Rows = condo
    ? [
        [
          `Charges de copropriété (ordre de grandeur ${condo.millesime})`,
          `${formatDecimal(condo.charges_m2_an)} €/m²/an, moyenne ${condo.territoire}`,
        ],
      ]
    : []
  return {
    title: 'Marché immobilier',
    rows: [
      ...priceRows(dvf),
      ...rentRows,
      ...yieldRows,
      ...taxRows(sources.taxe_fonciere?.data),
      ...condoRows,
    ],
    table: dvf ? salesTable(dvf) : undefined,
  }
}

/** Mêmes verdicts et conseils qu'à l'écran, puis les compléments chiffrés. */
function riskRows(data: GeorisquesData, preventionPlan: boolean): Rows {
  const verdicts = riskIndicators(data, preventionPlan)
    .filter((indicator) => indicator.tone !== 'neutral')
    .map((indicator): [string, string] => [
      indicator.label,
      indicator.advice ? `${indicator.value}. ${indicator.advice}` : indicator.value,
    ])
  const seveso = data.seveso
  const sevesoRows: Rows = seveso
    ? [
        [
          `Sites Seveso (${formatDistance(seveso.rayon_m)})`,
          seveso.sites.map((site) => `${site.nom} (${formatDistance(site.distance_m)})`).join(', ') || 'Aucun',
        ],
      ]
    : []
  const disasterRows: Rows = data.catastrophes_naturelles
    ? [['Arrêtés de catastrophe naturelle', formatInteger(data.catastrophes_naturelles.nb_arretes)]]
    : []
  return [...verdicts, ...sevesoRows, ...groundRows(data), ...disasterRows]
}

/** Plans de prévention, passé industriel et cavités : les compléments de l'étape « risques ». */
function groundRows(data: GeorisquesData): Rows {
  const rows: Rows = []
  if (data.plans_prevention?.length) {
    rows.push(['Plans de prévention des risques (commune)', data.plans_prevention.map((plan) => plan.nom).join(' ; ')])
  }
  if (data.tri?.length) rows.push(['Territoire à risque important d’inondation', data.tri.join(', ')])
  const sites = data.anciens_sites_industriels
  if (sites?.plus_proches.length) {
    const nearest = sites.plus_proches[0]
    rows.push([
      `Anciens sites industriels (${formatDistance(sites.rayon_m)})`,
      `${formatInteger(sites.nb_sites)} recensés, le plus proche à ${formatDistance(nearest?.distance_m)}`,
    ])
  }
  const cavities = data.cavites
  if (cavities?.plus_proche) {
    rows.push([
      `Cavités souterraines (${formatDistance(cavities.rayon_m)})`,
      `${formatInteger(cavities.nb_cavites)} recensée(s), la plus proche à ${formatDistance(cavities.plus_proche.distance_m)}`,
    ])
  }
  return rows
}

function risks(sources: SourceResults): ReportSection {
  const data = sources.georisques?.data
  return { title: 'Risques naturels et technologiques', rows: data ? riskRows(data, inPreventionPlan(sources.urbanisme?.data)) : [] }
}

function easementRows(zoning: UrbanismeData | null | undefined): Rows {
  const easements = zoning?.servitudes ?? []
  if (!easements.length) return []
  return [['Servitudes d’utilité publique', easements.map((item) => `${item.categorie} (${item.code})`).join(' ; ')]]
}

function buildingRows(building: BatimentData | null | undefined): Rows {
  if (!building) return []
  const rows: Rows = []
  if (building.annee_construction) rows.push(['Année de construction du bâtiment', String(building.annee_construction)])
  if (building.nb_niveaux) rows.push(['Niveaux', String(building.nb_niveaux)])
  if (building.nb_logements) rows.push(['Logements dans le bâtiment', formatInteger(building.nb_logements)])
  if (building.dpe?.classe) rows.push(['Étiquette énergie du bâtiment', building.dpe.classe])
  if (building.copropriete) {
    rows.push([
      'Copropriété',
      `${formatInteger(building.copropriete.nb_lots)} lots, immatriculation ${building.copropriete.immatriculation ?? '—'}`,
    ])
  }
  if (building.monument_historique?.dans_perimetre) rows.push(['Monument historique', 'Bâtiment situé dans les abords protégés'])
  return rows
}

function planning(sources: SourceResults): ReportSection {
  const parcel = sources.cadastre?.data
  const permits = sources.permis_construire?.data
  const parcelRows: Rows = parcel
    ? [['Parcelle', `${parcel.identifiant ?? '—'} (${formatInteger(parcel.contenance_m2)} m²)`]]
    : []
  const zoneRows = (sources.urbanisme?.data?.zones ?? []).map(
    (zone): [string, string] => ['Zonage PLU', [zone.libelle, zone.libelle_long].filter(Boolean).join(' — ')],
  )
  const permitRows: Rows = permits
    ? [
        [`Permis en cours (${permits.rayon_m} m)`, formatInteger(permits.nb_permis)],
        [
          'Risque de vis-à-vis',
          permits.risque_vis_a_vis ? `Oui (${permits.nb_projets_a_risque} projet(s))` : 'Non détecté',
        ],
      ]
    : []
  return {
    title: 'Urbanisme',
    rows: [
      ...buildingRows(sources.batiment?.data),
      ...parcelRows,
      ...zoneRows,
      ...easementRows(sources.urbanisme?.data),
      ...permitRows,
    ],
  }
}

/** Classe de bruit la plus forte au point, telle qu'affichée à l'écran. */
function noiseLevel(noise: BruitData): string {
  const strongest = noise.sources[0]
  if (!strongest) return 'Moins de 55 dB(A)'
  return strongest.db_max === null
    ? `Plus de ${strongest.db_min} dB(A)`
    : `${strongest.db_min} à ${strongest.db_max} dB(A)`
}

function environment(sources: SourceResults): ReportSection {
  const dpe = sources.dpe?.data
  const sun = sources.ensoleillement?.data
  const air = sources.qualite_air?.data
  const energyRows: Rows = dpe
    ? [
        ['Étiquette énergie la plus fréquente', dpe.etiquette_dominante ?? '—'],
        ...(dpe.analyse?.message ? ([['Parc énergivore', dpe.analyse.message]] satisfies Rows) : []),
      ]
    : []
  const noise = sources.bruit?.data
  const noiseRows: Rows = noise ? [['Bruit des infrastructures (Lden)', `${noiseLevel(noise)}. ${noise.message}`]] : []
  const sunRows: Rows = sun
    ? [
        ['Ensoleillement annuel (relief seul)', `${sun.score.annuel} %`],
        ['Ensoleillement au solstice d’hiver', `${sun.score.solstice_hiver} %`],
        ...(sun.synthese ? ([['Exposition', sun.synthese]] satisfies Rows) : []),
      ]
    : []
  const airRows: Rows = air
    ? [
        [
          `Qualité de l’air (indice ATMO du ${formatDate(air.date)})`,
          `${air.qualificatif} (${air.indice} sur 6), source ${air.producteur ?? 'Atmo France'}`,
        ],
      ]
    : []
  return { title: 'Énergie et environnement', rows: [...energyRows, ...sunRows, ...airRows, ...noiseRows] }
}

function burglaryRow(crime: DelinquanceData | null | undefined): Rows {
  const burglaries = crime?.indicateurs.find((item) => item.indicateur === 'Cambriolages de logement')
  if (!crime || !burglaries?.est_diffuse) return []
  return [
    [
      `Cambriolages de logement (${crime.annee})`,
      `${formatInteger(burglaries.nombre)}, soit ${formatDecimal(burglaries.taux_pour_mille)} pour 1 000 hab.` +
        (burglaries.reperes?.departement == null ? '' : ` (département : ${formatDecimal(burglaries.reperes.departement)})`),
    ],
  ]
}

function schoolsTable(schools: EcolesData): ReportSection['table'] {
  return {
    head: ['Établissement', 'Type', 'IPS', 'Distance'],
    body: schools.etablissements.map((school) => [
      school.nom,
      `${SCHOOL_KIND_LABELS[school.type_etablissement]} ${school.secteur === 'prive' ? 'privé' : 'public'}`,
      formatDecimal(school.ips),
      formatDistance(school.distance_m),
    ]),
  }
}

const RENT_CONTROL_LABELS = {
  oui: 'Oui',
  partiel: 'Possible (certaines communes de l’intercommunalité)',
  non: 'Non',
} as const

function rentalRows(rental: MarcheLocatifData | null | undefined): Rows {
  if (!rental) return []
  const occupancy = rental.occupation
  const occupancyRows: Rows = occupancy
    ? [
        [
          `Occupation des logements (quartier ${occupancy.iris.nom ?? occupancy.iris.code})`,
          `${formatPercent(occupancy.part_locataires_pct)} de locataires, ` +
            `${formatPercent(occupancy.part_proprietaires_pct)} de propriétaires, ` +
            `${formatPercent(occupancy.part_vacants_pct)} de logements vacants`,
        ],
      ]
    : []
  const rule = rental.encadrement_loyers
  const ruleRows: Rows = rule
    ? [['Encadrement des loyers', [RENT_CONTROL_LABELS[rule.statut], rule.territoire].filter(Boolean).join(' — ')]]
    : []
  return [...occupancyRows, ...ruleRows, ['Permis de louer', 'À vérifier en mairie (pas de recensement national)']]
}

function connectivityRows(connectivity: ConnectiviteData | null | undefined): Rows {
  if (!connectivity) return []
  return [
    [
      'Fibre optique (moyenne de la commune)',
      `${formatPercent(connectivity.part_fibre_pct)} des locaux raccordables`,
    ],
  ]
}

function mobileRows(mobile: ReseauMobileData | null | undefined): Rows {
  if (!mobile) return []
  const operators = mobile.operateurs.map((operator) => `${operator.nom} (${operator.generations.join(', ')})`)
  const note = mobile.liste_tronquee ? ' — liste partielle, zone très dense' : ''
  return [
    [
      `Réseau mobile (${formatInteger(mobile.nb_sites)} site${mobile.nb_sites > 1 ? 's' : ''} d’antennes à ${formatDistance(mobile.rayon_m)})`,
      `${operators.join(' ; ')}${note}`,
    ],
  ]
}

function neighbourhood(sources: SourceResults): ReportSection {
  const nearby = sources.proximite?.data
  const schools = sources.ecoles?.data
  const nearbyRows = orderedCategories(nearby?.categories ?? {}).map(([category, stats]): [string, string] => {
    const nearest = stats.plus_proche ? `, le plus proche à ${stats.plus_proche.marche_min} min` : ''
    const count = stats.nb ? `${formatInteger(stats.nb)} à moins de ${nearby?.rayon_m} m` : `Aucun à moins de ${nearby?.rayon_m} m`
    return [POI_CATEGORY_LABELS[category] ?? category, `${count}${nearest}`]
  })
  const walkingRows: Rows = nearbyRows.length
    ? [
        [
          'Temps de marche',
          nearby?.methode_temps === 'itineraire_pieton' ? 'Calculés sur itinéraire piéton' : 'Estimés à vol d’oiseau',
        ],
      ]
    : []
  const schoolRows: Rows = schools
    ? schoolAverages(schools)
    : []
  return {
    title: 'Vie de quartier',
    rows: [
      ...nearbyRows,
      ...walkingRows,
      ...schoolRows,
      ...burglaryRow(sources.delinquance?.data),
      ...rentalRows(sources.marche_locatif?.data),
      ...connectivityRows(sources.connectivite?.data),
      ...mobileRows(sources.reseau_mobile?.data),
    ],
    table: schools ? schoolsTable(schools) : undefined,
  }
}

/** Contenu textuel du rapport, indépendant du support (PDF, tests). */
const SCHOOL_LEVELS = [
  ['ecole', 'écoles'],
  ['college', 'collèges'],
  ['lycee', 'lycées'],
] as const

/** IPS moyen par niveau face à la moyenne nationale ; à défaut, la moyenne tous niveaux. */
function schoolAverages(schools: EcolesData): Rows {
  const rows = SCHOOL_LEVELS.flatMap(([id, label]): Rows => {
    const stats = schools.par_type?.[id]
    if (!stats) return []
    const reference = stats.moyenne_nationale === null ? '' : ` (France : ${formatDecimal(stats.moyenne_nationale)})`
    return [[`IPS moyen des ${label} proches`, `${formatDecimal(stats.ips_moyen)}${reference}`]]
  })
  const nearest = schools.superieur?.etablissements[0]
  if (nearest) {
    rows.push([
      `Enseignement supérieur (${formatDistance(schools.superieur?.rayon_m)})`,
      `${schools.superieur?.nb} établissement(s), le plus proche : ${nearest.nom} à ${formatDistance(nearest.distance_m)}`,
    ])
  }
  if (rows.length) return rows
  return schools.etablissements.length ? [['IPS moyen des établissements proches', formatDecimal(schools.ips_moyen)]] : []
}

/** Synthèse en tête du PDF : une ligne par constat, alertes d'abord. */
export function synthesisSections(synthesis: ReportSynthesis | null | undefined): ReportSection[] {
  if (!synthesis) return []
  const rows: Rows = [
    ...synthesis.alertes.map((item): [string, string] => [`Attention · ${item.theme}`, `${item.titre}. ${item.detail}`]),
    ...synthesis.points_forts.map((item): [string, string] => [`Point fort · ${item.theme}`, `${item.titre}. ${item.detail}`]),
  ]
  return rows.length ? [{ title: 'L’essentiel', rows }] : []
}

export function buildReportSections(sources: SourceResults): ReportSection[] {
  return [market, risks, planning, environment, neighbourhood]
    .map((build) => build(sources))
    .filter((section) => section.rows.length > 0)
}

/** Sources dont les données manquent au rapport, à signaler au lecteur. */
export function unavailableSources(sources: SourceResults): string[] {
  return Object.entries(sources)
    .filter(([, result]) => isFailure(result.status))
    .map(([name]) => name)
}
