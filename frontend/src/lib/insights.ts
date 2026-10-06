/** Présentation des risques : libellés et couleurs. Les recommandations viennent du serveur. */

import type { GeorisquesData } from '../types/audit'

export type Tone = 'good' | 'warn' | 'bad' | 'neutral'

export interface RiskIndicator {
  label: string
  value: string
  tone: Tone
  /** Ce que l'acheteur peut faire, quand le niveau le justifie. */
  advice?: string
}

type Verdict = Omit<RiskIndicator, 'label'>

const UNKNOWN: Verdict = { value: 'Non renseigné', tone: 'neutral' }

/** Niveau numérique -> ton : favorable sous `warnFrom`, défavorable à partir de `badFrom`. */
function toneForLevel(level: number, warnFrom: number, badFrom: number): Tone {
  if (level >= badFrom) return 'bad'
  return level >= warnFrom ? 'warn' : 'good'
}

function flood(data: GeorisquesData, inPreventionPlan: boolean): Verdict {
  // Seul constat établi à l'adresse : la servitude d'un plan de prévention couvre le point.
  if (inPreventionPlan) {
    return { value: 'Adresse dans le périmètre d’un plan de prévention des risques', tone: 'bad' }
  }
  if (!data.inondation) return UNKNOWN
  return data.inondation.concerne
    ? // Constat communal : l'atlas ne dit pas si l'adresse elle-même est exposée.
      {
        value: `Commune concernée par un atlas des zones inondables (${data.inondation.atlas_zones_inondables.join(', ')})`,
        tone: 'warn',
      }
    : // Neutre, pas vert : l'atlas ne couvre ni les PPRI ni les remontées de nappe.
      { value: 'Non répertorié dans l’atlas des zones inondables', tone: 'neutral' }
}

function clay(data: GeorisquesData): Verdict {
  const level = Number(data.argiles?.code)
  if (!data.argiles?.exposition || !Number.isFinite(level)) return UNKNOWN
  // En mode « rue », le niveau le plus fort rencontré le long de la voie est retenu.
  const value = data.argiles.variable ? `${data.argiles.exposition} au plus fort, variable le long de la rue` : data.argiles.exposition
  return { value, tone: toneForLevel(level, 2, 3) }
}

function seismic(data: GeorisquesData): Verdict {
  const level = Number(data.sismicite?.code)
  if (!data.sismicite?.zone || !Number.isFinite(level)) return UNKNOWN
  return { value: `Zone ${data.sismicite.zone.toLowerCase()}`, tone: toneForLevel(level, 3, 4) }
}

function radon(data: GeorisquesData): Verdict {
  const level = Number(data.radon?.classe_potentiel)
  if (!data.radon?.classe_potentiel || !Number.isFinite(level)) return UNKNOWN
  return { value: `Potentiel de catégorie ${level} sur 3`, tone: toneForLevel(level, 2, 3) }
}

/** Verdict de chaque risque ; la recommandation est celle calculée par le serveur. */
/** Vrai si une servitude de plan de prévention des risques naturels (PM1) couvre le point audité. */
export function inPreventionPlan(zoning: { servitudes?: unknown } | null | undefined): boolean {
  const easements = zoning?.servitudes
  // En aperçu gratuit, le serveur remplace la liste par une chaîne : rien n'est alors affirmé.
  return Array.isArray(easements) && easements.some((item: { code?: unknown }) => item.code === 'PM1')
}

const PREVENTION_PLAN_ADVICE =
  'Le règlement du plan peut limiter les travaux et peser sur l’assurance : demandez l’état des risques au vendeur.'

/**
 * Verdict par risque. `preventionPlan` vient de l'urbanisme : c'est le seul signal d'inondation
 * propre à l'adresse, les autres valant pour toute la commune.
 */
export function riskIndicators(data: GeorisquesData, preventionPlan = false): RiskIndicator[] {
  const advice = data.recommandations ?? {}
  return [
    {
      label: 'Inondation et risques naturels réglementés',
      ...flood(data, preventionPlan),
      advice: preventionPlan ? PREVENTION_PLAN_ADVICE : advice.inondation,
    },
    { label: 'Retrait-gonflement des argiles', ...clay(data), advice: advice.argiles },
    { label: 'Sismicité', ...seismic(data), advice: advice.sismicite },
    { label: 'Radon', ...radon(data), advice: advice.radon },
  ]
}
