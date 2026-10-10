import type { CommuneLink, CommuneProfile } from '../lib/commune'
import { API_URL } from './audit'

export type { CommuneLink }

const HTTP_NOT_FOUND = 404

/** Fiche d'une commune ; null si le code ne correspond à aucune commune. */
export async function fetchCommune(code: string): Promise<CommuneProfile | null> {
  const response = await fetch(`${API_URL}/api/v1/communes/${encodeURIComponent(code)}`)
  if (response.status === HTTP_NOT_FOUND) return null
  if (!response.ok) throw new Error(`communes ${response.status}`)
  return (await response.json()) as CommuneProfile
}

// Liste chargée avant l'affichage de la page (garde de la route) : la vue la lit sans attendre,
// et la page écrite en HTML à la construction n'est pas remplacée par une liste vide.
let links: CommuneLink[] = []

/** Communes disposant d'une page, liste produite à la construction du site. */
export function communeLinks(): CommuneLink[] {
  return links
}

/** Charge la liste une fois ; un échec la laisse vide et sera retenté à la prochaine visite. */
export async function loadCommuneLinks(): Promise<void> {
  if (links.length) return
  try {
    const response = await fetch('/communes.json')
    const payload: unknown = response.ok ? await response.json() : []
    links = Array.isArray(payload) ? (payload as CommuneLink[]) : []
  } catch {
    links = []
  }
}
