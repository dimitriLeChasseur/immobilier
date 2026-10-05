import type { AuditLocation, ReportMeta, SourceName, SourceResult } from '../types/audit'

function withoutTrailingSlashes(url: string): string {
  let end = url.length
  while (end > 0 && url[end - 1] === '/') end -= 1
  return url.slice(0, end)
}

const API_URL = withoutTrailingSlashes(import.meta.env.VITE_API_URL ?? 'http://localhost')

export interface AuditTarget {
  lat: number
  lon: number
  banId: string
}

export interface AuditStreamHandlers {
  onLocation: (location: AuditLocation) => void
  onSource: (name: SourceName, result: SourceResult) => void
  onDone: (meta: ReportMeta) => void
  onError: (message: string) => void
}

const CONNECTION_ERROR = "Impossible de joindre le service d'audit. Vérifiez votre connexion et réessayez."

function streamUrl(target: AuditTarget): string {
  const url = new URL(`${API_URL}/api/v1/audit/stream`)
  url.searchParams.set('lat', String(target.lat))
  url.searchParams.set('lon', String(target.lon))
  if (target.banId) url.searchParams.set('ban_id', target.banId)
  return url.toString()
}

function parse<T>(event: Event): T | null {
  try {
    return JSON.parse((event as MessageEvent<string>).data) as T
  } catch {
    return null
  }
}

/** Ordre et noms des sources, pour afficher les squelettes avant toute réponse. */
export async function fetchSourceNames(signal?: AbortSignal): Promise<SourceName[]> {
  const response = await fetch(`${API_URL}/api/v1/sources`, { signal })
  if (!response.ok) throw new Error(`sources ${response.status}`)
  const payload = (await response.json()) as { sources: SourceName[] }
  return payload.sources
}

/**
 * Ouvre le flux d'audit (Server-Sent Events). Renvoie la fonction d'annulation.
 * Le flux est fermé dès `done` ou `error` : EventSource ne doit pas se reconnecter,
 * sous peine de relancer un audit complet.
 */
export function openAuditStream(target: AuditTarget, handlers: AuditStreamHandlers): () => void {
  const source = new EventSource(streamUrl(target))
  let finished = false
  const close = (): void => {
    finished = true
    source.close()
  }

  source.addEventListener('location', (event) => {
    const location = parse<AuditLocation>(event)
    if (location) handlers.onLocation(location)
  })
  source.addEventListener('source', (event) => {
    const payload = parse<{ name: SourceName; result: SourceResult }>(event)
    if (payload) handlers.onSource(payload.name, payload.result)
  })
  source.addEventListener('done', (event) => {
    const meta = parse<ReportMeta>(event)
    close()
    if (meta) handlers.onDone(meta)
  })
  // `error` : soit un évènement métier émis par le serveur (avec données), soit une coupure réseau.
  source.addEventListener('error', (event) => {
    if (finished) return
    const payload = 'data' in event ? parse<{ detail?: string }>(event) : null
    close()
    handlers.onError(payload?.detail ?? CONNECTION_ERROR)
  })

  return close
}
