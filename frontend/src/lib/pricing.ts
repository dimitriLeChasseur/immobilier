/** Grille tarifaire affichée. Le montant débité est fixé côté serveur (backend/app/services/billing.py). */

export interface Offer {
  id: 'unit' | 'pack' | 'pro'
  name: string
  price: string
  /** Précision fiscale et rythme de facturation. */
  priceNote: string
  description: string
  /** Comparaison au prix à l'unité, sous le prix. */
  anchor?: string
  features: string[]
  cta: string
  highlighted: boolean
}

/** Plafond d'usage de l'offre Pro, appliqué par le serveur (PRO_DAILY_ADDRESS_LIMIT). */
export const PRO_DAILY_ADDRESSES = 150

/** Prix de l'audit à l'unité, repris dans les boutons de déblocage. */
export const UNIT_PRICE = '2,99 €'

/** Ce que tout visiteur obtient sans compte ni paiement. */
export const FREE_OFFER = {
  name: 'Aperçu gratuit',
  price: '0 €',
  priceNote: 'sans compte',
  description: 'Les chiffres de la commune et un aperçu de ce que l’audit a trouvé à cette adresse.',
  features: [
    'Loyers, taxe foncière, délinquance et fibre de la commune',
    'Qualité de l’air et risques recensés',
    'Nombre de ventes, de diagnostics et de permis analysés',
  ],
  cta: 'Analyser une adresse',
} as const

export const OFFERS: readonly Offer[] = [
  {
    id: 'unit',
    name: 'Contre-Visite',
    price: UNIT_PRICE,
    priceNote: 'TTC, paiement unique',
    description: 'Une adresse, tout vérifié avant de faire une offre. Le PDF à apporter à la seconde visite.',
    features: [
      'Prix des ventes voisines, rendement et synthèse',
      'Bâtiment, DPE, bruit, permis, écoles, carte',
      'Export PDF et checklist de seconde visite',
    ],
    cta: `Payer ${UNIT_PRICE}`,
    highlighted: false,
  },
  {
    id: 'pack',
    name: 'Pack Investisseur',
    price: '19,99 €',
    priceNote: 'TTC, paiement unique',
    description: 'Vous visitez plusieurs biens ? Passez-les tous au même crible.',
    // 10 × 2,99 € = 29,90 € : le pack en coûte 19,99 €, soit un tiers de moins.
    anchor: `2,00 € l’audit au lieu de ${UNIT_PRICE} · −33 %`,
    features: ['10 audits complets, sans date limite', 'Export PDF de chaque adresse', 'Une adresse débloquée en un clic'],
    cta: 'Payer 19,99 €',
    highlighted: true,
  },
  {
    id: 'pro',
    name: 'Pro',
    price: '49,00 €',
    priceNote: 'HT par mois',
    description: 'Pour les agents et chasseurs immobiliers : un dossier à votre logo pour chaque bien présenté.',
    features: [
      `Jusqu’à ${PRO_DAILY_ADDRESSES} nouvelles adresses par jour`,
      'PDF en marque blanche, à votre logo',
      'Résiliable à tout moment depuis votre compte',
    ],
    cta: 'S’abonner',
    highlighted: false,
  },
]
