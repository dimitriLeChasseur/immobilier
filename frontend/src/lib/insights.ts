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

function flood(data: GeorisquesData): Verdict {
  if (!data.inondation) return UNKNOWN
  return data.inondation.concerne
    ? {
        value: `Zone inondable (${data.inondation.atlas_zones_inondables.join(', ')})`,
        tone: 'bad',
      }
    : { value: 'Hors atlas des zones inondables', tone: 'good' }
}

function clay(data: GeorisquesData): Verdict {
  const level = Number(data.argiles?.code)
  if (!data.argiles?.exposition || !Number.isFinite(level)) return UNKNOWN
  return { value: data.argiles.exposition, tone: toneForLevel(level, 2, 3) }
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
export function riskIndicators(data: GeorisquesData): RiskIndicator[] {
  const advice = data.recommandations ?? {}
  return [
    { label: 'Inondation', ...flood(data), advice: advice.inondation },
    { label: 'Retrait-gonflement des argiles', ...clay(data), advice: advice.argiles },
    { label: 'Sismicité', ...seismic(data), advice: advice.sismicite },
    { label: 'Radon', ...radon(data), advice: advice.radon },
  ]
}
