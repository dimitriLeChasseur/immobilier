import type { AuditTarget } from '../api/audit'

/** Adresse que l'utilisateur veut débloquer, conservée pendant l'inscription et le paiement. */
export interface PendingAudit extends AuditTarget {
  label: string
}

const STORAGE_KEY = 'audit-immobilier.adresse-a-debloquer'

function isPendingAudit(value: unknown): value is PendingAudit {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.lat === 'number' &&
    typeof candidate.lon === 'number' &&
    Number.isFinite(candidate.lat) &&
    Number.isFinite(candidate.lon) &&
    typeof candidate.banId === 'string' &&
    typeof candidate.label === 'string'
  )
}

export function savePendingAudit(audit: PendingAudit): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(audit))
  } catch {
    // Stockage indisponible (navigation privée stricte) : le parcours continue sans mémoire.
  }
}

export function readPendingAudit(): PendingAudit | null {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null')
    return isPendingAudit(parsed) ? parsed : null
  } catch {
    return null
  }
}

export function clearPendingAudit(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Rien à nettoyer.
  }
}
