import type { SourceResults } from '../types/audit'
import { formatDate, formatInteger, formatPricePerM2 } from './format'

export type MarkerKind = 'vente' | 'ecole' | 'permis'

export interface MapMarker {
  kind: MarkerKind
  lat: number
  lon: number
  label: string
  /** Nombre d'éléments réunis en ce point (ventes d'un même immeuble). */
  weight?: number
}

export const MARKER_STYLES: Record<MarkerKind, { color: string; legend: string }> = {
  vente: { color: '#0d9488', legend: 'Ventes' },
  ecole: { color: '#7c3aed', legend: 'Établissements scolaires' },
  permis: { color: '#ea580c', legend: 'Permis de construire' },
}

function isPosition(lat: unknown, lon: unknown): boolean {
  return typeof lat === 'number' && typeof lon === 'number' && Number.isFinite(lat) && Number.isFinite(lon)
}

/** Une liste masquée par le serveur (aperçu gratuit) arrive sous forme de chaîne : elle est ignorée. */
function listOf<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : []
}

type Sale = [lon: number, lat: number, pricePerM2: number, count: number, lastYear: number]

function saleLabel(price: number, count: number, lastYear: number): string {
  if (count > 1) return `${count} ventes, médiane ${formatPricePerM2(price)} (dernière en ${lastYear})`
  return `Vente de ${lastYear} : ${formatPricePerM2(price)}`
}
type Positioned = { lat?: number; lon?: number }

/** Ventes, écoles et permis à placer sur la carte, d'après les données reçues. */
export function mapMarkers(sources: SourceResults): MapMarker[] {
  const sales = listOf<Sale>(sources.dvf?.data?.points)
    .filter((sale) => Array.isArray(sale) && isPosition(sale[1], sale[0]))
    .map(([lon, lat, price, count, lastYear]): MapMarker => ({
      kind: 'vente',
      lat,
      lon,
      label: saleLabel(price, count, lastYear),
      weight: count,
    }))
  const schools = listOf<Positioned & { nom: string; ips: number }>(sources.ecoles?.data?.etablissements)
    .filter((school) => isPosition(school.lat, school.lon))
    .map((school): MapMarker => ({
      kind: 'ecole',
      lat: school.lat as number,
      lon: school.lon as number,
      label: `${school.nom} (IPS ${formatInteger(school.ips)})`,
    }))
  const permits = listOf<Positioned & { adresse: string | null; date_autorisation: string }>(
    sources.permis_construire?.data?.permis,
  )
    .filter((permit) => isPosition(permit.lat, permit.lon))
    .map((permit): MapMarker => ({
      kind: 'permis',
      lat: permit.lat as number,
      lon: permit.lon as number,
      label: `Permis du ${formatDate(permit.date_autorisation)}${permit.adresse ? `, ${permit.adresse}` : ''}`,
    }))
  return [...sales, ...schools, ...permits]
}
