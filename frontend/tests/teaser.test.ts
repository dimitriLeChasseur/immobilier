import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import { parseSseBuffer } from '../src/api/audit'
import LockedOverlay from '../src/components/LockedOverlay.vue'
import SourceCard from '../src/components/SourceCard.vue'
import { clearPendingAudit, readPendingAudit, savePendingAudit } from '../src/lib/pending'
import { OFFERS } from '../src/lib/pricing'
import { SOURCE_INFO } from '../src/lib/sources'
import { isLocked, LOCKED, teaserHook } from '../src/lib/teaser'
import { UNLOCK_KEY } from '../src/lib/unlock'
import PricingView from '../src/views/PricingView.vue'

const ADDRESS = { lat: 47.470656, lon: -0.551674, banId: '49007_6630_00012', label: '12 Place du Ralliement 49100 Angers' }

describe('flux SSE lu avec fetch', () => {
  it('découpe les évènements complets et garde le reliquat', () => {
    const { events, rest } = parseSseBuffer(
      'event: location\ndata: {"label":"Angers"}\n\nevent: source\ndata: {"name":"dvf"}\n\nevent: done\ndata: {"acc',
    )
    expect(events).toEqual([
      { event: 'location', data: '{"label":"Angers"}' },
      { event: 'source', data: '{"name":"dvf"}' },
    ])
    expect(rest).toBe('event: done\ndata: {"acc')
  })

  it('reconstitue un évènement arrivé en deux morceaux', () => {
    const first = parseSseBuffer('event: done\ndata: {"access":')
    const second = parseSseBuffer(`${first.rest}"teaser"}\n\n`)
    expect(first.events).toEqual([])
    expect(second.events).toEqual([{ event: 'done', data: '{"access":"teaser"}' }])
    expect(second.rest).toBe('')
  })
})

describe('détection des valeurs masquées par le serveur', () => {
  it('repère la valeur verrouillée à tout niveau', () => {
    expect(isLocked({ nb_ventes: 505, prix_m2_median: LOCKED })).toBe(true)
    expect(isLocked({ categories: { transports: { nb: 3, plus_proche: LOCKED } } })).toBe(true)
    expect(isLocked({ nb_ventes: 505, zones: [{ libelle: 'UG' }] })).toBe(false)
    expect(isLocked(null)).toBe(false)
  })

  it('formule une accroche à partir des seules valeurs lisibles', () => {
    expect(teaserHook('dvf', { nb_ventes: 505, rayon_m: 300, prix_m2_median: LOCKED })).toBe(
      '505 ventes analysées à moins de 300 m',
    )
    expect(teaserHook('georisques', { risques: ['Inondation', 'Radon'], radon: LOCKED })).toBe(
      '2 risques recensés sur la commune',
    )
    expect(
      teaserHook('proximite', { rayon_m: 500, categories: { transports: { nb: 35, plus_proche: LOCKED }, sante: { nb: 11, plus_proche: LOCKED } } }),
    ).toBe('46 équipements repérés à moins de 500 m')
    expect(teaserHook('cadastre', { identifiant: LOCKED })).toBe('Analyse réalisée pour cette adresse')
    // Une valeur masquée n'est jamais reprise dans l'accroche.
    expect(teaserHook('dvf', { nb_ventes: LOCKED })).not.toContain('LOCKED')
  })
})

describe('carte verrouillée', () => {
  const open = vi.fn()
  const provide = { [UNLOCK_KEY as symbol]: { open, label: computed(() => 'Débloquer l’audit complet pour 4,99 €') } }
  const slots = { default: ({ data }: { data: unknown }) => `prix ${JSON.stringify(data)}` }
  const result = { status: 'ok' as const, data: { nb_ventes: 505, prix_m2_median: LOCKED }, missing: [], error: null, duration_ms: 3 }

  it('affiche l’accroche et un contenu factice flouté, jamais la carte de données', () => {
    const card = mount(SourceCard, {
      props: { ...SOURCE_INFO.dvf, result, hook: '505 ventes analysées à moins de 300 m' },
      slots,
      global: { provide },
    })
    expect(card.text()).toContain('505 ventes analysées à moins de 300 m')
    expect(card.text()).not.toContain('LOCKED')
    expect(card.text()).not.toContain('prix {')
    const blurred = card.find('.locked-blur')
    expect(blurred.exists()).toBe(true)
    expect(blurred.attributes('aria-hidden')).toBe('true')
    expect(card.find('button').text()).toBe('Débloquer l’audit complet pour 4,99 €')
  })

  it('affiche normalement une source entièrement lisible', () => {
    const clear = { ...result, data: { indice: 3, qualificatif: 'Dégradé' } }
    const card = mount(SourceCard, { props: { ...SOURCE_INFO.qualite_air, result: clear }, slots, global: { provide } })
    expect(card.find('.locked-blur').exists()).toBe(false)
    expect(card.text()).toContain('prix {')
  })

  it('déclenche le déblocage au clic, avec un libellé court sur les petites cartes', async () => {
    const overlay = mount(LockedOverlay, { props: { compact: true }, global: { provide } })
    const button = overlay.find('button')
    expect(button.text()).toBe('Débloquer')
    expect(button.attributes('aria-label')).toContain('pour 4,99 €')
    await button.trigger('click')
    expect(open).toHaveBeenCalledTimes(1)
  })
})

describe('adresse mémorisée pendant l’inscription', () => {
  beforeEach(() => localStorage.clear())

  it('fait l’aller-retour dans le stockage local', () => {
    savePendingAudit(ADDRESS)
    expect(readPendingAudit()).toEqual(ADDRESS)
    clearPendingAudit()
    expect(readPendingAudit()).toBeNull()
  })

  it('ignore un contenu absent, corrompu ou falsifié', () => {
    expect(readPendingAudit()).toBeNull()
    localStorage.setItem('audit-immobilier.adresse-a-debloquer', '{pas du json')
    expect(readPendingAudit()).toBeNull()
    localStorage.setItem('audit-immobilier.adresse-a-debloquer', JSON.stringify({ lat: 'x', lon: 2, banId: '', label: '' }))
    expect(readPendingAudit()).toBeNull()
  })
})

describe('grille tarifaire', () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'audit', component: { template: '<div />' } },
      { path: '/tarifs', name: 'pricing', component: PricingView },
      { path: '/cgv', name: 'terms', component: { template: '<div />' } },
    ],
  })
  beforeEach(() => localStorage.clear())

  it('présente les trois offres aux bons prix, le pack investisseur mis en avant au centre', () => {
    expect(OFFERS.map((offer) => [offer.name, offer.price, offer.priceNote, offer.cta])).toEqual([
      ['Contre-Visite', '4,99 €', 'TTC, paiement unique', 'Payer 4,99 €'],
      ['Pack Investisseur', '24,99 €', 'TTC, paiement unique', 'Payer 24,99 €'],
      ['Pro', '49,00 €', 'HT par mois', 'S’abonner'],
    ])
    expect(OFFERS.map((offer) => offer.highlighted)).toEqual([false, true, false])

    const view = mount(PricingView, { global: { plugins: [router] } })
    const cards = view.findAll('ul > li.relative')
    expect(cards).toHaveLength(3)
    expect(cards[1]?.classes()).toContain('border-brand-600')
    expect(cards[1]?.text()).toContain('Le plus avantageux')
    // L'aperçu gratuit a sa propre colonne, avant les offres payantes.
    expect(view.find('ul > li').text()).toContain('Aperçu gratuit')
    expect(view.find('ul > li').text()).toContain('0 €')
    expect(view.text()).toContain('Voir un rapport d’exemple')
    expect(view.text()).toContain('Audit de Due Diligence complet pour 1 adresse + Export PDF.')
    expect(view.text()).toContain('Rapports sans décompte + Export en marque blanche (Votre logo).')
  })

  it('rappelle l’adresse à débloquer et demande une connexion avant tout paiement', async () => {
    savePendingAudit(ADDRESS)
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const AuthModal = { props: ['open'], template: '<div data-test="auth" :data-open="open" />' }
    const view = mount(PricingView, { global: { plugins: [router], stubs: { AuthModal } } })
    expect(view.text()).toContain('12 Place du Ralliement 49100 Angers')
    expect(view.text()).toContain('Paiement sécurisé par Stripe')

    await view.findAll('li.relative > button')[1]?.trigger('click')
    // Sans session, aucun appel de paiement ne part : la fenêtre de connexion s'ouvre.
    expect(fetchMock).not.toHaveBeenCalled()
    expect(view.find('[data-test="auth"]').attributes('data-open')).toBe('true')
    vi.unstubAllGlobals()
  })
})
