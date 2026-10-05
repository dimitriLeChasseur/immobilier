import type { AuditTarget } from '../api/audit'

/** Cible d'audit lue dans l'URL (lien partageable), ou null si absente ou invalide. */
export function readTarget(search: string): (AuditTarget & { label: string }) | null {
  const params = new URLSearchParams(search)
  const rawLat = params.get('lat')
  const rawLon = params.get('lon')
  if (rawLat === null || rawLon === null) return null
  const lat = Number(rawLat)
  const lon = Number(rawLon)
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
    return null
  }
  return { lat, lon, banId: params.get('ban_id') ?? '', label: (params.get('q') ?? '').slice(0, 200) }
}

export function writeTarget(target: AuditTarget, label: string): string {
  const params = new URLSearchParams({ lat: String(target.lat), lon: String(target.lon) })
  if (target.banId) params.set('ban_id', target.banId)
  if (label) params.set('q', label)
  return `?${params.toString()}`
}
