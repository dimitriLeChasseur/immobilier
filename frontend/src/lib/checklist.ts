/** Points que les données publiques ne permettent pas de vérifier : à contrôler par l'acheteur. */

export interface ChecklistItem {
  id: string
  label: string
}

export const CHECKLIST_TITLE = 'Checklist de Contre-Visite'

export const CHECKLIST_ITEMS: readonly ChecklistItem[] = [
  {
    id: 'fibre',
    label: 'Demander au vendeur la facture de la fibre optique (donnée publique exacte indisponible).',
  },
  {
    id: 'permis_louer',
    label: 'Vérifier en mairie si l’adresse est soumise au permis de louer.',
  },
  {
    id: 'dpe',
    label: 'Demander le DPE complet du logement (le rapport ne montre que ceux du voisinage).',
  },
]
