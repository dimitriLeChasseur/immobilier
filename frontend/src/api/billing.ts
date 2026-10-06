import type { Offer } from '../lib/pricing'
import { API_URL, type AuditTarget } from './audit'

/** Compte de l'utilisateur connecté (miroir de backend/app/api/routers/billing.py). */
export interface Account {
  email: string | null
  credits: number
  subscription_active: boolean
}

export interface BillingAddress extends AuditTarget {
  label: string
}

const FALLBACK_ERROR = 'Le service de paiement ne répond pas. Réessayez dans un instant.'

/** Échec d'un appel de paiement ; `status` est le code HTTP, 0 si le serveur est injoignable. */
export class BillingError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'BillingError'
    this.status = status
  }
}

function addressBody(address: BillingAddress): Record<string, unknown> {
  return { lat: address.lat, lon: address.lon, ban_id: address.banId, label: address.label }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()
    const detail = (body as { detail?: unknown } | null)?.detail
    return typeof detail === 'string' ? detail : FALLBACK_ERROR
  } catch {
    return FALLBACK_ERROR
  }
}

async function call<T>(path: string, accessToken: string, body?: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_URL}/api/v1/${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new BillingError(0, FALLBACK_ERROR)
  }
  if (!response.ok) throw new BillingError(response.status, await errorMessage(response))
  return (await response.json()) as T
}

export function fetchAccount(accessToken: string): Promise<Account> {
  return call<Account>('account', accessToken)
}

/** Crée la session de paiement et renvoie l'adresse de la page Stripe. */
export async function startCheckout(
  accessToken: string,
  offer: Offer['id'],
  address: BillingAddress | null,
): Promise<string> {
  const body = { offer, address: address ? addressBody(address) : null }
  return (await call<{ url: string }>('checkout', accessToken, body)).url
}

/** Débloque une adresse avec un crédit ; échoue en 402 s'il n'en reste aucun. */
export function unlockWithCredit(accessToken: string, address: BillingAddress): Promise<Account> {
  return call<Account>('unlock', accessToken, addressBody(address))
}

/** Adresse du portail Stripe (factures, moyen de paiement, résiliation). */
export async function openBillingPortal(accessToken: string): Promise<string> {
  return (await call<{ url: string }>('billing/portal', accessToken, {})).url
}
