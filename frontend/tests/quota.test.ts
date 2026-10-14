import { afterEach, describe, expect, it, vi } from 'vitest'

import { openAuditStream, type AuditStreamHandlers } from '../src/api/audit'
import { DEMO_QUERY, DEMO_TARGET } from '../src/lib/demo'
import { FREE_OFFER, OFFERS, PRO_DAILY_ADDRESSES, UNIT_PRICE } from '../src/lib/pricing'
import { readTarget } from '../src/lib/url'

const TARGET = { lat: 47.47, lon: -0.55, banId: '' }

/** Ouvre le flux contre une réponse simulée et renvoie le message d'erreur reçu. */
async function refusal(response: Response): Promise<string> {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
  return new Promise((resolve) => {
    const handlers: AuditStreamHandlers = {
      onLocation: () => undefined,
      onAccess: () => undefined,
      onSource: () => undefined,
      onDone: () => resolve('terminé sans erreur'),
      onError: resolve,
    }
    openAuditStream(TARGET, handlers)
  })
}

describe('refus du serveur à l’ouverture du flux', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('affiche le message du serveur quand un quota est atteint', async () => {
    const detail = 'Limite d’aperçus gratuits atteinte : créez un compte ou réessayez plus tard.'
    await expect(refusal(new Response(JSON.stringify({ detail }), { status: 429 }))).resolves.toBe(detail)
  })

  it('garde un message générique si la réponse 429 n’est pas lisible', async () => {
    await expect(refusal(new Response('<html>', { status: 429 }))).resolves.toBe(
      'Trop de requêtes, réessayez dans un instant.',
    )
  })

  it('ne répète pas le détail technique des autres erreurs', async () => {
    const message = await refusal(new Response(JSON.stringify({ detail: 'trace interne' }), { status: 500 }))
    expect(message).not.toContain('trace interne')
    await expect(refusal(new Response('', { status: 401 }))).resolves.toContain('session a expiré')
  })

  it('transmet le plafond quotidien de l’offre Pro signalé dans le flux', async () => {
    const body = 'event: error\ndata: {"code":"daily_limit_reached","detail":"Plafond quotidien atteint."}\n\n'
    await expect(refusal(new Response(body, { status: 200 }))).resolves.toBe('Plafond quotidien atteint.')
  })
})

describe('déroulé du flux', () => {
  afterEach(() => vi.unstubAllGlobals())

  const LOCATION = 'event: location\ndata: {"lat":47.47,"lon":-0.55,"label":"Angers","citycode":"49007"}\n\n'
  const SOURCE = 'event: source\ndata: {"name":"dvf","result":{"status":"empty","data":null}}\n\n'

  /** Rejoue un corps de flux et note, dans l'ordre, ce que reçoit l'interface. */
  async function replay(body: string): Promise<string[]> {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status: 200 })))
    const received: string[] = []
    return new Promise((resolve) => {
      openAuditStream(TARGET, {
        onLocation: (location) => received.push(`location:${location.label}`),
        onAccess: (access) => received.push(`access:${access}`),
        onSource: (name) => received.push(`source:${name}`),
        onDone: () => resolve([...received, 'done']),
        onError: (message) => resolve([...received, `error:${message}`]),
      })
    })
  }

  it('annonce le niveau d’accès dès la localisation, avant les cartes', async () => {
    const body = `${LOCATION}event: access\ndata: {"access":"teaser"}\n\n${SOURCE}event: done\ndata: {"access":"teaser"}\n\n`
    expect(await replay(body)).toEqual(['location:Angers', 'access:teaser', 'source:dvf', 'done'])
  })

  it('signale une coupure en plein flux sans perdre les cartes déjà reçues', async () => {
    // Connexion perdue (tunnel, mise en veille du téléphone) avant l'évènement final.
    const events = await replay(`${LOCATION}${SOURCE}`)
    expect(events.slice(0, 2)).toEqual(['location:Angers', 'source:dvf'])
    expect(events.at(-1)).toContain('Impossible de joindre le service d')
  })
})

describe('offre gratuite et rapport d’exemple', () => {
  it('décrit le gratuit et annonce le prix à l’unité repris par les boutons', () => {
    expect(FREE_OFFER.price).toBe('0 €')
    expect(FREE_OFFER.features.join(' ')).toContain('taxe foncière')
    expect(OFFERS[0]?.price).toBe(UNIT_PRICE)
    expect(OFFERS.find((offer) => offer.id === 'pro')?.features[0]).toContain(String(PRO_DAILY_ADDRESSES))
  })

  it('pointe le rapport d’exemple par un lien que la page d’accueil sait relire', () => {
    const target = readTarget(`?${new URLSearchParams(DEMO_QUERY).toString()}`)
    expect(target).toMatchObject({ lat: DEMO_TARGET.lat, lon: DEMO_TARGET.lon, banId: DEMO_TARGET.banId })
    expect(target?.label).toContain('Angers')
  })
})
