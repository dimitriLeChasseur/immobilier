import type { QuartierData } from '../types/audit'
import { formatDistance, formatEuros, formatInteger, formatPercent } from './format'

/** Textes du profil de quartier, partagés par la carte à l'écran et le PDF. */

export interface Notice {
  title: string
  detail: string
}

/** Périmètre dans lequel un logement neuf peut bénéficier de la TVA réduite autour d'un quartier prioritaire. */
const REDUCED_VAT_RADIUS_M = 300

function signed(value: number): string {
  return `${value > 0 ? '+' : ''}${formatPercent(value)}`
}

/** Écart du niveau de vie médian du quartier à la médiane nationale de la même année. */
export function incomeGap(income: QuartierData['revenus']): string | null {
  const reference = income?.reference_nationale?.revenu_median
  if (!income?.revenu_median || !reference) return null
  const gap = Math.round((100 * (income.revenu_median - reference)) / reference)
  if (gap === 0) return `au niveau de la médiane nationale (${formatEuros(reference)})`
  return `${Math.abs(gap)} % ${gap > 0 ? 'au-dessus' : 'en dessous'} de la médiane nationale (${formatEuros(reference)})`
}

/** Fourchette dans laquelle se situe la moitié des habitants du quartier. */
export function incomeRange(income: QuartierData['revenus']): string | null {
  if (!income?.revenu_q1 || !income.revenu_q3) return null
  return `La moitié des habitants vit avec ${formatEuros(income.revenu_q1)} à ${formatEuros(income.revenu_q3)} par an`
}

/** Territoire que décrivent les revenus : le quartier, ou la commune quand il n'est pas diffusé. */
export function incomeScope(profile: Pick<QuartierData, 'iris' | 'revenus'>): string {
  const income = profile.revenus
  if (income?.echelle === 'commune') return income.arrondissement ? 'Arrondissement entier' : 'Commune entière'
  const quarter = profile.iris?.nom ?? profile.iris?.code
  return quarter ? `Quartier « ${quarter} »` : 'Quartier'
}

export function districtNotice(district: QuartierData['quartier_prioritaire']): Notice | null {
  if (!district) return null
  if (!district.nom) {
    return {
      title: 'Hors quartier prioritaire',
      detail: `Aucun quartier prioritaire de la politique de la ville à moins de ${formatDistance(district.rayon_m)}.`,
    }
  }
  if (district.dans_un_quartier) {
    return {
      title: `Dans le quartier prioritaire « ${district.nom} »`,
      detail:
        'Périmètre de la politique de la ville (2024). L’achat d’un logement neuf en résidence principale peut y ' +
        'ouvrir droit, sous conditions de ressources, à une TVA réduite : à vérifier auprès du vendeur.',
    }
  }
  const nearEnough = (district.distance_m ?? Infinity) <= REDUCED_VAT_RADIUS_M
  return {
    title: `À ${formatDistance(district.distance_m)} du quartier prioritaire « ${district.nom} »`,
    detail: nearEnough
      ? 'L’adresse est hors du périmètre, mais dans la bande de 300 m où un logement neuf peut bénéficier, sous ' +
        'conditions de ressources, d’une TVA réduite : à vérifier auprès du vendeur.'
      : 'L’adresse est hors du périmètre de la politique de la ville (2024).',
  }
}

/** Évolution de la population sur onze ans, ou six à défaut ; null si aucune n'est connue. */
export function populationTrend(population: QuartierData['population']): string | null {
  if (!population) return null
  const eleven = population.evolution_11_ans_pct
  const six = population.evolution_6_ans_pct
  const parts = [
    typeof six === 'number' ? `${signed(six)} en 6 ans` : null,
    typeof eleven === 'number' ? `${signed(eleven)} en 11 ans` : null,
  ].filter((part) => part !== null)
  return parts.length ? parts.join(', ') : null
}

export function populationScope(population: NonNullable<QuartierData['population']>): string {
  const place = population.arrondissement ? 'de l’arrondissement' : 'de la commune'
  return `${formatInteger(population.habitants)} habitants ${place} (recensement ${population.annee})`
}
