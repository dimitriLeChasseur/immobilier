/**
 * Fiche d'une commune : mêmes textes à l'écran et dans la page statique générée à la
 * construction (scripts/seo.ts). Module sans dépendance, exécutable tel quel par Node.
 */

export interface Benchmark {
  valeur: number
  departement: number | null
  national: number | null
}

/** Miroir de backend/app/schemas/commune.py. */
export interface CommuneProfile {
  code: string
  nom: string
  slug: string
  departement_code: string
  departement_nom: string
  population: number | null
  codes_postaux: string[]
  centre: [number, number] | null
  taxe_fonciere: { annee: number; taux_tfb_total: Benchmark; taux_teom: number | null } | null
  delinquance: { annee: number; cambriolages: Benchmark; annee_precedente: number | null } | null
  ecoles: Partial<Record<string, { nb: number; ips_moyen: number; moyenne_nationale: number | null }>>
  part_fibre_pct: number | null
  /** Loyers d'annonce au m², charges comprises, par type de bien. */
  loyers?: Partial<Record<string, number>>
  /** Paris, Lyon, Marseille : loyers du moins cher et du plus cher des arrondissements. */
  loyers_fourchette?: Partial<Record<string, [number, number]>>
  /** Échelle de l'estimation par type de bien : « commune », « EPCI » ou « maille ». */
  loyers_niveau?: Partial<Record<string, string>>
  loyers_millesime?: number | null
  logement: {
    annee: number
    logements: number
    part_locataires_pct: number | null
    part_proprietaires_pct: number | null
    part_vacants_pct: number | null
  } | null
}

export interface CommuneFact {
  label: string
  value: string
  /** Repère ou précision affichée sous la valeur. */
  note?: string
}

export interface CommuneSection {
  heading: string
  facts: CommuneFact[]
}

export interface CommunePage {
  title: string
  description: string
  heading: string
  intro: string
  sections: CommuneSection[]
}

const SITE_NAME = 'Audit Immobilier'
// Variation au-delà de laquelle l'évolution sur un an est signalée.
const TREND_THRESHOLD = 0.1
const SCHOOL_LEVELS: [id: string, label: string][] = [
  ['ecole', 'Écoles'],
  ['college', 'Collèges'],
  ['lycee', 'Lycées'],
]

function decimal(value: number, digits = 1): string {
  return new Intl.NumberFormat('fr-FR', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value)
}

function integer(value: number): string {
  return new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 }).format(value)
}

function percent(value: number, digits = 1): string {
  return `${decimal(value, digits)} %`
}

function benchmarkNote(benchmark: Benchmark, format: (value: number) => string, departement: string): string | undefined {
  const parts = [
    benchmark.departement === null ? null : `${departement} : ${format(benchmark.departement)}`,
    benchmark.national === null ? null : `France : ${format(benchmark.national)}`,
  ].filter((part): part is string => part !== null)
  return parts.length ? parts.join(' · ') : undefined
}

function trend(current: number, previous: number | null): string {
  if (!previous) return ''
  const change = (current - previous) / previous
  if (Math.abs(change) < TREND_THRESHOLD) return ', stable sur un an'
  return change > 0 ? ', en hausse sur un an' : ', en baisse sur un an'
}

const RENT_KINDS: [id: string, label: string][] = [
  ['appartement', 'Appartement'],
  ['t1_t2', 'Appartement de 1 ou 2 pièces'],
  ['t3_plus', 'Appartement de 3 pièces et plus'],
  ['maison', 'Maison'],
]

/** Précision à donner quand le loyer n'est pas estimé sur les annonces de la commune seule. */
export function rentScope(level: string | null | undefined): string | undefined {
  if (level === 'maille') return 'Estimé sur un groupe de communes voisines au marché comparable'
  if (level === 'EPCI') return 'Estimé à l’échelle de l’intercommunalité'
  return undefined
}

function rentNote(profile: CommuneProfile, id: string): string | undefined {
  const range = profile.loyers_fourchette?.[id]
  const notes = [
    range ? `De ${decimal(range[0])} à ${decimal(range[1])} €/m² selon l’arrondissement` : undefined,
    rentScope(profile.loyers_niveau?.[id]),
  ].filter((note) => note !== undefined)
  return notes.length ? notes.join(' · ') : undefined
}

function rentSection(profile: CommuneProfile): CommuneSection | null {
  const facts = RENT_KINDS.flatMap(([id, label]): CommuneFact[] => {
    const rent = profile.loyers?.[id]
    if (typeof rent !== 'number') return []
    return [{ label, value: `${decimal(rent)} €/m² par mois, charges comprises`, note: rentNote(profile, id) }]
  })
  const year = profile.loyers_millesime
  const heading = year ? `Loyers d’annonce (estimation ${year})` : 'Loyers d’annonce'
  return facts.length ? { heading, facts } : null
}

/** Les territoires que la carte des loyers ne couvre pas le disent, au lieu d'un silence. */
function rentGap(profile: CommuneProfile, hasOtherFigures: boolean): CommuneSection | null {
  if (!hasOtherFigures || Object.keys(profile.loyers ?? {}).length) return null
  return {
    heading: 'Loyers d’annonce',
    facts: [
      {
        label: 'Loyers',
        value: 'Non disponibles',
        note: 'Cette commune ne figure pas dans la carte des loyers (ANIL), qui ne couvre ni Mayotte ni les collectivités d’outre-mer.',
      },
    ],
  }
}

function taxSection(profile: CommuneProfile): CommuneSection | null {
  const tax = profile.taxe_fonciere
  if (!tax) return null
  const facts: CommuneFact[] = [
    {
      label: `Taux global de taxe foncière sur le bâti (${tax.annee})`,
      value: percent(tax.taux_tfb_total.valeur, 2),
      note: benchmarkNote(tax.taux_tfb_total, (value) => percent(value, 2), `Commune médiane du département`),
    },
  ]
  if (tax.taux_teom !== null) {
    facts.push({ label: 'Taxe d’enlèvement des ordures ménagères', value: percent(tax.taux_teom, 2) })
  }
  return { heading: 'Fiscalité locale', facts }
}

function crimeSection(profile: CommuneProfile): CommuneSection | null {
  const crime = profile.delinquance
  if (!crime) return null
  const rate = crime.cambriolages
  return {
    heading: 'Sécurité',
    facts: [
      {
        label: `Cambriolages de logement (${crime.annee})`,
        value: `${decimal(rate.valeur)} pour 1 000 habitants${trend(rate.valeur, crime.annee_precedente)}`,
        note: benchmarkNote(rate, (value) => decimal(value), profile.departement_nom || 'Département'),
      },
    ],
  }
}

function schoolSection(profile: CommuneProfile): CommuneSection | null {
  const facts = SCHOOL_LEVELS.flatMap(([id, label]): CommuneFact[] => {
    const level = profile.ecoles[id]
    if (!level) return []
    return [
      {
        label: `${label} (${level.nb})`,
        value: `Indice de position sociale moyen : ${decimal(level.ips_moyen)}`,
        note: level.moyenne_nationale === null ? undefined : `France : ${decimal(level.moyenne_nationale)}`,
      },
    ]
  })
  return facts.length ? { heading: 'Établissements scolaires', facts } : null
}

function housingSection(profile: CommuneProfile): CommuneSection | null {
  const housing = profile.logement
  const facts: CommuneFact[] = []
  if (housing) {
    facts.push({ label: `Logements (recensement ${housing.annee})`, value: integer(housing.logements) })
    if (housing.part_locataires_pct !== null) {
      facts.push({ label: 'Résidences principales louées', value: percent(housing.part_locataires_pct) })
    }
    if (housing.part_vacants_pct !== null) {
      facts.push({ label: 'Logements vacants', value: percent(housing.part_vacants_pct) })
    }
  }
  if (profile.part_fibre_pct !== null) {
    facts.push({ label: 'Locaux raccordables à la fibre', value: percent(profile.part_fibre_pct) })
  }
  return facts.length ? { heading: 'Logement et connexion', facts } : null
}

/** Titre, description et contenu de la fiche d'une commune. */
export function communePage(profile: CommuneProfile): CommunePage {
  const place = `${profile.nom} (${profile.departement_code})`
  const figures = [
    rentSection(profile),
    taxSection(profile),
    crimeSection(profile),
    schoolSection(profile),
    housingSection(profile),
  ].filter((section): section is CommuneSection => section !== null)
  const gap = rentGap(profile, figures.length > 0)
  const sections = gap ? [gap, ...figures] : figures
  // Le millésime entre parenthèses reste dans le titre de rubrique, pas dans la description.
  const topics = figures.map((section) => section.heading.replace(/ \(.*\)$/, '').toLowerCase()).join(', ')
  const population = profile.population === null ? '' : `, ${integer(profile.population)} habitants`
  return {
    title: `Immobilier à ${place} : loyers, taxe foncière, sécurité, écoles | ${SITE_NAME}`,
    description:
      `Chiffres clés pour acheter à ${profile.nom}${population} : ${topics || 'données publiques'}. ` +
      'Auditez ensuite une adresse précise : ventes voisines, risques, bâtiment.',
    heading: `Acheter à ${profile.nom}`,
    intro:
      `${profile.nom} (${profile.departement_nom || profile.departement_code}${population}) en quelques chiffres publics, ` +
      'comparés au département et à la France. Ces données valent pour toute la commune : pour une adresse précise, ' +
      'lancez un audit.',
    sections,
  }
}

/** Segment d'URL d'une commune : « angers-49007 » (même règle que le serveur). */
export function communeSlug(name: string, code: string): string {
  const plain = name
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return `${plain}-${code.toLowerCase()}`
}

/** Code INSEE porté par un segment d'URL « angers-49007 », null s'il n'en a pas la forme. */
export function codeFromSlug(slug: string): string | null {
  const code = (slug.split('-').pop() ?? '').toUpperCase()
  return /^[0-9][0-9AB][0-9]{3}$/.test(code) ? code : null
}
