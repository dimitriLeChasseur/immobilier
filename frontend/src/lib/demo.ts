import type { AuditTarget } from '../api/audit'
import { writeTarget } from './url'

/**
 * Adresse du rapport d'exemple, ouvert à tous sans compte ni paiement.
 *
 * Le serveur ne sert le rapport complet que pour l'identifiant déclaré dans sa variable
 * DEMO_ADDRESS_ID : les deux doivent désigner la même adresse. Sans elle, ce lien mène à
 * l'aperçu gratuit ordinaire.
 */
export const DEMO_TARGET: AuditTarget = { lat: 47.46976, lon: -0.553891, banId: '49007_7050_00010' }
export const DEMO_LABEL = '10 Rue Saint-Aubin 49100 Angers'

/** Paramètres d'URL du rapport d'exemple, pour un lien vers la page d'accueil. */
export const DEMO_QUERY: Record<string, string> = Object.fromEntries(
  new URLSearchParams(writeTarget(DEMO_TARGET, DEMO_LABEL)),
)
