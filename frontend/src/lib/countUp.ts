/**
 * Compteur animé d'une valeur déjà mise en forme (« 3 859 €/m² », « 6,2 % ») : on retrouve le
 * nombre dans le texte, puis on réécrit chaque étape avec la même présentation.
 */

// Entier avec séparateurs de milliers français (espace fine insécable, insécable ou simple),
// suivi d'une éventuelle partie décimale après la virgule.
const NUMBER = /(\d{1,3}(?:[   ]\d{3})+|\d+)(?:,(\d+))?/
const GROUP = /[   ]/

export interface NumberParts {
  before: string
  after: string
  value: number
  decimals: number
  /** Séparateur de milliers d'origine, repris tel quel. */
  group: string
}

/** Premier nombre du texte et ce qui l'entoure ; null s'il n'y en a pas. */
export function splitNumber(text: string): NumberParts | null {
  const match = NUMBER.exec(text)
  if (!match) return null
  const [whole, integerPart = '', fraction = ''] = match
  return {
    before: text.slice(0, match.index),
    after: text.slice(match.index + whole.length),
    value: Number(integerPart.replace(new RegExp(GROUP.source, 'g'), '') + (fraction ? `.${fraction}` : '')),
    decimals: fraction.length,
    group: GROUP.exec(integerPart)?.[0] ?? ' ',
  }
}

/** Réécrit `value` avec la présentation du texte d'origine. */
export function formatLike(parts: NumberParts, value: number): string {
  const [integer = '0', fraction] = value.toFixed(parts.decimals).split('.')
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, parts.group)
  return `${parts.before}${grouped}${fraction ? `,${fraction}` : ''}${parts.after}`
}

/** Décélération en fin de course : le chiffre se pose au lieu de s'arrêter net. */
export function easeOut(progress: number): number {
  return 1 - (1 - progress) ** 3
}
