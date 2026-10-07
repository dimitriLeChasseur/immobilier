import { call } from './billing'

/** Adresse débloquée par l'utilisateur (miroir de backend/app/api/routers/account.py). */
export interface UnlockedAudit {
  label: string | null
  lat: number
  lon: number
  ban_id: string | null
  origin: 'unit' | 'pack' | 'subscription' | 'admin'
  granted_at: string
}

/** Marque blanche de l'offre Pro : nom et logo repris en tête des rapports PDF. */
export interface Branding {
  company: string
  /** URL « data: » d'un PNG ou d'un JPEG, ou null sans logo. */
  logo: string | null
  /** Couleur du bandeau et des titres (« #rrggbb ») ; null : couleur par défaut. */
  color?: string | null
  /** Coordonnées du professionnel, imprimées sous l'en-tête. */
  phone?: string | null
  email?: string | null
  website?: string | null
  address?: string | null
}

export function fetchAudits(accessToken: string): Promise<UnlockedAudit[]> {
  return call<UnlockedAudit[]>('account/audits', accessToken)
}

/** Null sans marque enregistrée ou sans abonnement actif. */
export function fetchBranding(accessToken: string): Promise<Branding | null> {
  return call<Branding | null>('account/branding', accessToken)
}

export function saveBranding(accessToken: string, branding: Branding): Promise<Branding> {
  return call<Branding>('account/branding', accessToken, branding, 'PUT')
}

export async function deleteBranding(accessToken: string): Promise<void> {
  await call<unknown>('account/branding', accessToken, undefined, 'DELETE')
}
