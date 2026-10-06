import { afterEach, describe, expect, it, vi } from 'vitest'

import { BillingError, fetchAccount, openBillingPortal, startCheckout, unlockWithCredit } from '../src/api/billing'

const ADDRESS = { lat: 48.86, lon: 2.33, banId: '75101_1234_00001', label: '1 rue de Rivoli' }

function respond(status: number, body: unknown): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function sentRequest(fetchMock: ReturnType<typeof vi.fn>): { url: string; init: RequestInit; body: unknown } {
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
  return { url, init, body: typeof init.body === 'string' ? JSON.parse(init.body) : undefined }
}

describe('appels de paiement', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('demande une session de paiement sans transmettre de montant', async () => {
    const fetchMock = respond(200, { url: 'https://checkout.stripe.com/c/pay/cs_test_1' })

    await expect(startCheckout('jeton', 'unit', ADDRESS)).resolves.toBe('https://checkout.stripe.com/c/pay/cs_test_1')

    const { url, init, body } = sentRequest(fetchMock)
    expect(url).toMatch(/\/api\/v1\/checkout$/)
    expect(init.method).toBe('POST')
    expect(init.headers).toMatchObject({ Authorization: 'Bearer jeton' })
    expect(body).toEqual({
      offer: 'unit',
      address: { lat: 48.86, lon: 2.33, ban_id: '75101_1234_00001', label: '1 rue de Rivoli' },
    })
  })

  it('achète un pack ou un abonnement sans adresse', async () => {
    const fetchMock = respond(200, { url: 'https://checkout.stripe.com/x' })
    await startCheckout('jeton', 'pro', null)
    expect(sentRequest(fetchMock).body).toEqual({ offer: 'pro', address: null })
  })

  it('lit le compte avec une requête GET', async () => {
    const account = { email: 'a@example.org', credits: 3, subscription_active: false }
    const fetchMock = respond(200, account)
    await expect(fetchAccount('jeton')).resolves.toEqual(account)
    expect(sentRequest(fetchMock).init.method).toBe('GET')
  })

  it('débloque une adresse avec un crédit', async () => {
    const fetchMock = respond(200, { email: null, credits: 2, subscription_active: false })
    await expect(unlockWithCredit('jeton', ADDRESS)).resolves.toMatchObject({ credits: 2 })
    expect(sentRequest(fetchMock).url).toMatch(/\/api\/v1\/unlock$/)
  })

  it('ouvre le portail de gestion de l’abonnement', async () => {
    const fetchMock = respond(200, { url: 'https://billing.stripe.com/p/session/1' })
    await expect(openBillingPortal('jeton')).resolves.toBe('https://billing.stripe.com/p/session/1')
    expect(sentRequest(fetchMock).url).toMatch(/\/api\/v1\/billing\/portal$/)
  })

  it('restitue le message du serveur et le code HTTP en cas de refus', async () => {
    respond(402, { detail: 'Aucun crédit disponible.' })
    const failure = await unlockWithCredit('jeton', ADDRESS).catch((error: unknown) => error)
    expect(failure).toBeInstanceOf(BillingError)
    expect(failure).toMatchObject({ status: 402, message: 'Aucun crédit disponible.' })
  })

  it('reste lisible quand le serveur est injoignable ou répond hors format', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('réseau')))
    await expect(fetchAccount('jeton')).rejects.toMatchObject({ status: 0 })

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>', { status: 502 })))
    await expect(fetchAccount('jeton')).rejects.toMatchObject({
      status: 502,
      message: 'Le service de paiement ne répond pas. Réessayez dans un instant.',
    })
  })
})
