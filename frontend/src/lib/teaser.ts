import type { SourceName } from '../types/audit'
import { formatInteger } from './format'

/** Valeur renvoyée par le serveur à la place d'une donnée réservée aux audits achetés. */
export const LOCKED = '***LOCKED***'

/** Vrai si les données d'une source contiennent au moins une valeur masquée par le serveur. */
export function isLocked(data: unknown): boolean {
  if (data === LOCKED) return true
  if (Array.isArray(data)) return data.some(isLocked)
  if (typeof data === 'object' && data !== null) return Object.values(data).some(isLocked)
  return false
}

/** Nombre lisible, ou null si la valeur est absente ou masquée. */
function count(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

type Data = Record<string, unknown>
type Hook = (data: Data) => string | null

function sentence(value: unknown, build: (n: number) => string): string | null {
  const n = count(value)
  return n === null ? null : build(n)
}

function poiTotal(data: Data): string | null {
  const categories = data.categories
  if (typeof categories !== 'object' || categories === null) return null
  const total = Object.values(categories as Record<string, { nb?: unknown }>).reduce(
    (sum, category) => sum + (count(category?.nb) ?? 0),
    0,
  )
  return `${formatInteger(total)} équipements repérés à moins de ${formatInteger(count(data.rayon_m))} m`
}

function riskCount(data: Data): string | null {
  const risks = data.risques
  return Array.isArray(risks) ? `${risks.length} risques recensés sur la commune` : null
}

// Ce que l'on peut dire sans rien révéler : la preuve que l'analyse a eu lieu.
const HOOKS: Partial<Record<SourceName, Hook>> = {
  dvf: (d) => sentence(d.nb_ventes, (n) => `${formatInteger(n)} ventes analysées à moins de ${formatInteger(count(d.rayon_m))} m`),
  georisques: riskCount,
  reseau_mobile: (d) => sentence(d.nb_sites, (n) => `${formatInteger(n)} sites d’antennes repérés à proximité`),
  permis_construire: (d) => sentence(d.nb_permis, (n) => `${formatInteger(n)} autorisation(s) d’urbanisme en cours à proximité`),
  dpe: (d) => sentence(d.nb_dpe_analyses, (n) => `${formatInteger(n)} diagnostics énergétiques analysés`),
  proximite: poiTotal,
  loyers: (d) => sentence(d.nb_observations, (n) => `Loyer estimé à partir de ${formatInteger(n)} annonces`),
  connectivite: (d) => sentence(d.nb_locaux, (n) => `${formatInteger(n)} locaux analysés dans la commune`),
  delinquance: (d) => sentence(d.annee, (n) => `Statistiques ${n} de la commune analysées`),
  taxe_fonciere: (d) => sentence(d.annee, (n) => `Taux ${n} de la commune relevés`),
}

const DEFAULT_HOOK = 'Analyse réalisée pour cette adresse'

/** Phrase d'accroche affichée au-dessus du contenu flouté d'une source verrouillée. */
export function teaserHook(source: SourceName, data: unknown): string {
  if (typeof data !== 'object' || data === null) return DEFAULT_HOOK
  return HOOKS[source]?.(data as Data) ?? DEFAULT_HOOK
}
