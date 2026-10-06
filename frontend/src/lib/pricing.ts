/** Grille tarifaire affichée. Le montant débité est fixé côté serveur (backend/app/services/billing.py). */

export interface Offer {
  id: 'unit' | 'pack' | 'pro'
  name: string
  price: string
  /** Précision fiscale et rythme de facturation. */
  priceNote: string
  description: string
  features: string[]
  cta: string
  highlighted: boolean
}

export const OFFERS: readonly Offer[] = [
  {
    id: 'unit',
    name: 'Contre-Visite',
    price: '4,99 €',
    priceNote: 'TTC, paiement unique',
    description: 'Audit de Due Diligence complet pour 1 adresse + Export PDF.',
    features: ['1 audit complet', 'Export PDF', 'Checklist de contre-visite'],
    cta: 'Payer 4,99 €',
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
    description: 'Rapports illimités + Export en marque blanche (Votre logo).',
    features: ['Audits illimités', 'PDF à votre logo', 'Pour agents et chasseurs immobiliers'],
    cta: 'S’abonner',
    highlighted: false,
  },
]
