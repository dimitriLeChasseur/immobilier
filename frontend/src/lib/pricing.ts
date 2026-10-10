/** Grille tarifaire affichée. Le montant débité est fixé côté serveur (backend/app/services/billing.py). */

export interface Offer {
  id: 'unit' | 'pack5' | 'pack' | 'pro'
  name: string
  price: string
  /** Précision fiscale et rythme de facturation. */
  priceNote: string
  description: string
  features: string[]
  cta: string
  highlighted: boolean
}

/** Plafond d'usage de l'offre Pro, appliqué par le serveur (PRO_DAILY_ADDRESS_LIMIT). */
export const PRO_DAILY_ADDRESSES = 150

/** Prix de l'audit à l'unité, repris dans les boutons de déblocage. */
export const UNIT_PRICE = '4,99 €'

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
    description: 'Audit de Due Diligence complet pour 1 adresse + Export PDF.',
    features: [
      'Prix des ventes voisines, rendement et synthèse',
      'Bâtiment, DPE, bruit, permis, écoles, carte',
      'Export PDF et checklist de contre-visite',
    ],
    cta: `Payer ${UNIT_PRICE}`,
    highlighted: false,
  },
  {
    id: 'pack5',
    name: 'Pack Visites',
    price: '14,99 €',
    priceNote: 'TTC, paiement unique',
    description: 'Pack de 5 audits complets. Pour départager les biens d’une même recherche.',
    features: ['5 audits complets', 'Export PDF de chaque adresse', 'Soit 3,00 € par audit'],
    cta: 'Payer 14,99 €',
    highlighted: false,
  },
  {
    id: 'pack',
    name: 'Pack Investisseur',
    price: '24,99 €',
    priceNote: 'TTC, paiement unique',
    description: 'Pack de 10 audits complets. Idéal pour comparer plusieurs biens lors de vos visites.',
    features: ['10 audits complets', 'Export PDF de chaque adresse', 'Soit 2,50 € par audit'],
    cta: 'Payer 24,99 €',
    highlighted: true,
  },
  {
    id: 'pro',
    name: 'Pro',
    price: '49,00 €',
    priceNote: 'HT par mois',
    description: 'Rapports sans décompte + Export en marque blanche (Votre logo).',
    features: [
      `Jusqu’à ${PRO_DAILY_ADDRESSES} nouvelles adresses par jour`,
      'PDF à votre logo',
      'Pour agents et chasseurs immobiliers',
    ],
    cta: 'S’abonner',
    highlighted: false,
  },
]
