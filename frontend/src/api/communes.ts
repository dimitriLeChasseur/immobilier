import type { CommuneProfile } from '../lib/commune'
import { API_URL } from './audit'

export interface CommuneLink {
  nom: string
  slug: string
  departement_code: string
}

const HTTP_NOT_FOUND = 404

/** Fiche d'une commune ; null si le code ne correspond à aucune commune. */
export async function fetchCommune(code: string): Promise<CommuneProfile | null> {
  const response = await fetch(`${API_URL}/api/v1/communes/${encodeURIComponent(code)}`)
  if (response.status === HTTP_NOT_FOUND) return null
  if (!response.ok) throw new Error(`communes ${response.status}`)
  return (await response.json()) as CommuneProfile
}

/** Communes disposant d'une page, liste produite à la construction du site. */
export async function fetchCommuneLinks(): Promise<CommuneLink[]> {
  const response = await fetch('/communes.json')
  if (!response.ok) return []
  const payload: unknown = await response.json()
  return Array.isArray(payload) ? (payload as CommuneLink[]) : []
}
