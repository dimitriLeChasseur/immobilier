/** Calcul de la taxe foncière à partir de la valeur locative cadastrale d'un avis d'impôt. */

// La base d'imposition est la valeur locative cadastrale diminuée d'un abattement forfaitaire
// de 50 % pour frais (article 1388 du code général des impôts).
const TAXABLE_SHARE = 0.5
// Plafond de saisie : écarte une confusion avec un prix de vente.
export const MAX_RENTAL_VALUE = 500_000

export interface PropertyTaxEstimate {
  /** Base d'imposition (« revenu cadastral ») en euros. */
  taxableBase: number
  /** Taxe foncière sur le bâti, au taux global. */
  propertyTax: number
  /** Taxe d'enlèvement des ordures ménagères, null si la commune n'en lève pas ici. */
  wasteTax: number | null
  total: number
}

/**
 * Montants annuels estimés, hors frais de gestion ajoutés par l'administration.
 * Renvoie null tant que la valeur saisie n'est pas un montant plausible.
 */
export function estimatePropertyTax(
  rentalValue: number | null,
  globalRatePct: number,
  wasteRatePct: number | null,
): PropertyTaxEstimate | null {
  if (rentalValue === null || !Number.isFinite(rentalValue)) return null
  if (rentalValue <= 0 || rentalValue > MAX_RENTAL_VALUE) return null
  const taxableBase = rentalValue * TAXABLE_SHARE
  const propertyTax = (taxableBase * globalRatePct) / 100
  const wasteTax = wasteRatePct === null ? null : (taxableBase * wasteRatePct) / 100
  return { taxableBase, propertyTax, wasteTax, total: propertyTax + (wasteTax ?? 0) }
}
