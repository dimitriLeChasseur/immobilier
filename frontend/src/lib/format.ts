/** Mise en forme française des valeurs affichées. `—` quand la valeur est absente. */

const EMPTY = '—'
/** Nombre minimal de ventes d'appartements pour avancer un rendement. */
export const MIN_SALES_FOR_YIELD = 5

const integer = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 })
const euros = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })
const longDate = new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })

type Maybe = number | null | undefined

export function formatInteger(value: Maybe): string {
  return value == null ? EMPTY : integer.format(value)
}

export function formatDecimal(value: Maybe, digits = 1): string {
  if (value == null) return EMPTY
  return new Intl.NumberFormat('fr-FR', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value)
}

export function formatEuros(value: Maybe): string {
  return value == null ? EMPTY : euros.format(value)
}

export function formatPricePerM2(value: Maybe): string {
  return value == null ? EMPTY : `${euros.format(value)}/m²`
}

export function formatPercent(value: Maybe, digits = 1): string {
  return value == null ? EMPTY : `${formatDecimal(value, digits)} %`
}

export function formatDistance(metres: Maybe): string {
  if (metres == null) return EMPTY
  return metres < 1000 ? `${integer.format(metres)} m` : `${formatDecimal(metres / 1000)} km`
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return EMPTY
  // "20260616" (Géoportail de l'urbanisme) -> "2026-06-16"
  const normalized = /^\d{8}$/.test(iso) ? `${iso.slice(0, 4)}-${iso.slice(4, 6)}-${iso.slice(6)}` : iso
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? EMPTY : longDate.format(date)
}

/**
 * Prix médian des appartements vendus à proximité, seul comparable au loyer d'appartement.
 * Null si la valeur est masquée par le serveur ou s'il y a trop peu de ventes d'appartements.
 */
export function flatPrice(dvf: { par_type?: unknown; recent?: unknown } | null | undefined): number | null {
  // Les 24 derniers mois s'ils comptent assez de ventes, sinon les cinq ans.
  const recent = (dvf?.recent as { par_type?: unknown } | null | undefined)?.par_type
  return flatMedian(recent) ?? flatMedian(dvf?.par_type)
}

function flatMedian(byKind: unknown): number | null {
  if (typeof byKind !== 'object' || byKind === null) return null
  const flats = (byKind as Record<string, { prix_m2_median?: unknown; nb_ventes?: unknown } | undefined>).appartement
  // Une poignée de ventes ne fait pas un prix de marché (quartier pavillonnaire).
  if (typeof flats?.nb_ventes !== 'number' || flats.nb_ventes < MIN_SALES_FOR_YIELD) return null
  return typeof flats.prix_m2_median === 'number' ? flats.prix_m2_median : null
}

/** Rendement locatif brut annuel, en %. */
export function grossYield(rentPerM2: Maybe, pricePerM2: Maybe): number | null {
  if (rentPerM2 == null || pricePerM2 == null || pricePerM2 <= 0) return null
  return (rentPerM2 * 12 * 100) / pricePerM2
}

export interface YieldInputs {
  rentPerM2: number
  pricePerM2: number
  surfaceM2: number
  /** Montants annuels en euros à la charge du propriétaire. */
  propertyTax: number
  condoCharges: number
}

/** Rendement annuel net de taxe foncière et de charges, en % ; null si le calcul n'a pas de sens. */
export function netYield(inputs: YieldInputs): number | null {
  const price = inputs.pricePerM2 * inputs.surfaceM2
  if (!Number.isFinite(price) || price <= 0 || inputs.surfaceM2 <= 0) return null
  const income = inputs.rentPerM2 * 12 * inputs.surfaceM2 - inputs.propertyTax - inputs.condoCharges
  return (income * 100) / price
}

export function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}
