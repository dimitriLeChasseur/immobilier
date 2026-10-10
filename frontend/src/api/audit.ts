import type { AuditLocation, ReportMeta, SourceName, SourceResult } from '../types/audit'

function withoutTrailingSlashes(url: string): string {
  let end = url.length
  while (end > 0 && url[end - 1] === '/') end -= 1
  return url.slice(0, end)
}

export const API_URL = withoutTrailingSlashes(import.meta.env.VITE_API_URL ?? 'http://localhost')

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

export interface SseEvent {
  event: string
  data: string
}

const CONNECTION_ERROR = "Impossible de joindre le service d'audit. Vérifiez votre connexion et réessayez."
const SESSION_ERROR = 'Votre session a expiré. Reconnectez-vous pour relancer l’audit.'
const HTTP_UNAUTHORIZED = 401
const HTTP_TOO_MANY_REQUESTS = 429

function streamUrl(target: AuditTarget): string {
  const url = new URL(`${API_URL}/api/v1/audit/stream`)
  url.searchParams.set('lat', String(target.lat))
  url.searchParams.set('lon', String(target.lon))
  if (target.banId) url.searchParams.set('ban_id', target.banId)
  return url.toString()
}

/**
 * Découpe un tampon de flux Server-Sent Events en évènements complets.
 * Renvoie aussi le reliquat (évènement encore incomplet) à garder pour le prochain morceau.
 */
export function parseSseBuffer(buffer: string): { events: SseEvent[]; rest: string } {
  const blocks = buffer.split('\n\n')
  const rest = blocks.pop() ?? ''
  const events: SseEvent[] = []
  for (const block of blocks) {
    let event = 'message'
    const data: string[] = []
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
    }
    if (data.length) events.push({ event, data: data.join('\n') })
  }
  return { events, rest }
}

function parseJson<T>(text: string): T | null {
  try {
    return JSON.parse(text) as T
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

/** Traite un évènement ; renvoie vrai quand le flux est terminé (`done` ou `error`). */
function dispatch({ event, data }: SseEvent, handlers: AuditStreamHandlers): boolean {
  if (event === 'location') {
    const location = parseJson<AuditLocation>(data)
    if (location) handlers.onLocation(location)
  } else if (event === 'source') {
    const payload = parseJson<{ name: SourceName; result: SourceResult }>(data)
    if (payload) handlers.onSource(payload.name, payload.result)
  } else if (event === 'done') {
    const meta = parseJson<ReportMeta>(data)
    if (meta) handlers.onDone(meta)
    else handlers.onError(CONNECTION_ERROR)
    return true
  } else if (event === 'error') {
    handlers.onError(parseJson<{ detail?: string }>(data)?.detail ?? CONNECTION_ERROR)
    return true
  }
  return false
}

/** Message d'un refus du serveur : le sien pour un quota dépassé, générique sinon. */
async function refusalMessage(response: Response): Promise<string> {
  if (response.status === HTTP_UNAUTHORIZED) return SESSION_ERROR
  if (response.status !== HTTP_TOO_MANY_REQUESTS) return CONNECTION_ERROR
  const detail = parseJson<{ detail?: unknown }>(await response.text().catch(() => ''))?.detail
  return typeof detail === 'string' ? detail : 'Trop de requêtes, réessayez dans un instant.'
}

async function consume(response: Response, handlers: AuditStreamHandlers): Promise<void> {
  if (!response.ok || !response.body) {
    handlers.onError(await refusalMessage(response))
    return
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    const parsed = parseSseBuffer(buffer + decoder.decode(value, { stream: true }))
    buffer = parsed.rest
    if (parsed.events.some((event) => dispatch(event, handlers))) return
  }
  // Flux coupé avant l'évènement final.
  handlers.onError(CONNECTION_ERROR)
}

/**
 * Ouvre le flux d'audit (Server-Sent Events lus avec fetch) et renvoie la fonction d'annulation.
 * fetch remplace EventSource pour pouvoir transmettre le jeton de session en en-tête : sans
 * jeton, ou sans achat de l'adresse, le serveur renvoie la version « teaser » du rapport.
 */
export function openAuditStream(
  target: AuditTarget,
  handlers: AuditStreamHandlers,
  accessToken?: string | null,
): () => void {
  const controller = new AbortController()
  const headers: Record<string, string> = { Accept: 'text/event-stream' }
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`

  fetch(streamUrl(target), { headers, signal: controller.signal })
    .then((response) => consume(response, handlers))
    .catch(() => {
      if (!controller.signal.aborted) handlers.onError(CONNECTION_ERROR)
    })

  return () => controller.abort()
}
