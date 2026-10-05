/** Mise en forme française des valeurs affichées. `—` quand la valeur est absente. */

const EMPTY = '—'

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
