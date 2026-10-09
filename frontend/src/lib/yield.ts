/** Rendement locatif par type de bien : chaque loyer est rapporté au prix de biens comparables. */

import { grossYield, MIN_SALES_FOR_YIELD } from './format'

export type YieldKind = 'appartement' | 't1_t2' | 't3_plus' | 'maison'

export interface YieldLine {
  id: YieldKind
  label: string
  rentPerM2: number
  pricePerM2: number
  /** Ventes sur lesquelles repose le prix médian. */
  sales: number
  /** Rendement brut annuel, en %. */
  gross: number
}

const KINDS: [id: YieldKind, label: string][] = [
  ['appartement', 'Appartement, toutes tailles'],
  ['t1_t2', 'Appartement de 1 ou 2 pièces'],
  ['t3_plus', 'Appartement de 3 pièces et plus'],
  ['maison', 'Maison'],
]
/** En dessous, une surface d'appartement relève plutôt d'un 1 ou 2 pièces. */
const SMALL_FLAT_BELOW_M2 = 50

type Group = { prix_m2_median?: unknown; nb_ventes?: unknown }
type Groups = Record<string, Group | undefined>
interface Sales {
  par_type?: unknown
  par_taille?: unknown
  recent?: unknown
}
interface Rents {
  loyer_m2_charges_comprises?: unknown
  par_typologie?: unknown
}

function groupsOf(sales: unknown, kind: YieldKind): Group | undefined {
  const key = kind === 't1_t2' || kind === 't3_plus' ? 'par_taille' : 'par_type'
  const groups = (sales as Sales | null | undefined)?.[key]
  // Une valeur masquée par le serveur est une chaîne : elle ne donne aucun prix.
  return typeof groups === 'object' && groups !== null ? (groups as Groups)[kind] : undefined
}

function usable(group: Group | undefined): { price: number; sales: number } | null {
  // Une poignée de ventes ne fait pas un prix de marché.
  if (typeof group?.nb_ventes !== 'number' || group.nb_ventes < MIN_SALES_FOR_YIELD) return null
  return typeof group.prix_m2_median === 'number' ? { price: group.prix_m2_median, sales: group.nb_ventes } : null
}

/** Les 24 derniers mois s'ils comptent assez de ventes de ce type, sinon les cinq ans. */
function priceOf(dvf: Sales | null | undefined, kind: YieldKind): { price: number; sales: number } | null {
  return usable(groupsOf(dvf?.recent, kind)) ?? usable(groupsOf(dvf, kind))
}

function rentOf(rents: Rents | null | undefined, kind: YieldKind): number | null {
  if (kind === 'appartement') {
    return typeof rents?.loyer_m2_charges_comprises === 'number' ? rents.loyer_m2_charges_comprises : null
  }
  const byKind = rents?.par_typologie
  if (typeof byKind !== 'object' || byKind === null) return null
  const rent = (byKind as Record<string, { loyer_m2_charges_comprises?: unknown } | undefined>)[kind]
    ?.loyer_m2_charges_comprises
  return typeof rent === 'number' ? rent : null
}

/** Une ligne par type de bien dont le loyer et un prix de marché sont tous deux connus. */
export function yieldLines(rents: Rents | null | undefined, dvf: Sales | null | undefined): YieldLine[] {
  return KINDS.flatMap(([id, label]): YieldLine[] => {
    const rent = rentOf(rents, id)
    const market = priceOf(dvf, id)
    const gross = grossYield(rent, market?.price)
    if (rent === null || market === null || gross === null) return []
    return [{ id, label, rentPerM2: rent, pricePerM2: market.price, sales: market.sales, gross }]
  })
}

/** Type d'appartement que désigne une surface, parmi les lignes disponibles. */
export function lineForSurface(lines: YieldLine[], surfaceM2: number): YieldLine | null {
  const sized = surfaceM2 < SMALL_FLAT_BELOW_M2 ? 't1_t2' : 't3_plus'
  return (
    lines.find((line) => line.id === sized) ?? lines.find((line) => line.id === 'appartement') ?? lines[0] ?? null
  )
}
