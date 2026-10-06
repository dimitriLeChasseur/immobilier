import type { AddressSuggestion } from '../types/audit'

const BAN_SEARCH_URL = 'https://api-adresse.data.gouv.fr/search/'
export const MIN_QUERY_LENGTH = 3
const MAX_RESULTS = 6

interface BanFeature {
  geometry?: { coordinates?: unknown }
  properties?: { id?: unknown; label?: unknown; context?: unknown; type?: unknown }
}

function toSuggestion(feature: BanFeature): AddressSuggestion | null {
  const coordinates = feature.geometry?.coordinates
  const { id, label, context, type } = feature.properties ?? {}
  if (!Array.isArray(coordinates) || typeof id !== 'string' || typeof label !== 'string') {
    return null
  }
  const [lon, lat] = coordinates as unknown[]
  if (typeof lon !== 'number' || typeof lat !== 'number') return null
  return { id, label, context: typeof context === 'string' ? context : '', lat, lon, street: type === 'street' }
}

/** Suggestions d'adresses de la Base Adresse Nationale pour une saisie partielle. */
export async function searchAddresses(query: string, signal?: AbortSignal): Promise<AddressSuggestion[]> {
  const trimmed = query.trim()
  if (trimmed.length < MIN_QUERY_LENGTH) return []

  const url = new URL(BAN_SEARCH_URL)
  url.searchParams.set('q', trimmed.slice(0, 200))
  url.searchParams.set('limit', String(MAX_RESULTS))
  url.searchParams.set('autocomplete', '1')

  const response = await fetch(url, { signal })
  if (!response.ok) throw new Error(`BAN ${response.status}`)
  const payload = (await response.json()) as { features?: BanFeature[] }
  return (payload.features ?? []).map(toSuggestion).filter((item) => item !== null)
}
