import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { LEGAL_INCOMPLETE, PROCESSORS, PUBLISHER, TODO } from '../src/lib/legal'
import { LEGAL_DOCUMENTS } from '../src/lib/legalContent'
import { OFFERS } from '../src/lib/pricing'
import LegalView from '../src/views/LegalView.vue'

const text = (key: keyof typeof LEGAL_DOCUMENTS) =>
  LEGAL_DOCUMENTS[key].sections.flatMap((section) => [section.heading, ...section.paragraphs]).join('\n')

describe('pages légales', () => {
  it('reprend dans les CGV les prix réellement affichés sur la page Tarifs', () => {
    const cgv = text('cgv')
    for (const offer of OFFERS) {
      expect(cgv).toContain(offer.name)
      expect(cgv).toContain(offer.price)
    }
    expect(cgv).toContain('L. 221-28')
    expect(cgv).toContain('médiateur de la consommation')
    expect(cgv).toContain('résilié à tout moment')
  })

  it('nomme chaque prestataire qui reçoit des données et rappelle les droits', () => {
    const privacy = text('confidentialite')
    for (const processor of PROCESSORS) expect(privacy).toContain(processor.name)
    expect(privacy).toContain('CNIL')
    expect(privacy).toContain('ni cookie publicitaire, ni outil de mesure d’audience')
  })

  it('cite les hébergeurs et les licences des données dans les mentions légales', () => {
    const notice = text('mentions')
    expect(notice).toContain('Cloudflare, Inc.')
    expect(notice).toContain('Contabo GmbH')
    expect(notice).toContain('ODbL')
    expect(notice).toContain('ne remplacent ni la visite du bien')
  })

  it('signale à l’écran ce que l’éditeur doit encore compléter', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: ['legal-notice', 'terms', 'privacy'].map((name) => ({ path: `/${name}`, name, component: LegalView })),
    })
    const view = mount(LegalView, { props: { document: 'mentions' }, global: { plugins: [router] } })
    expect(view.find('h1').text()).toBe('Mentions légales')
    expect(view.findAll('nav a')).toHaveLength(3)
    const missing = Object.values(PUBLISHER).includes(TODO)
    expect(LEGAL_INCOMPLETE).toBe(missing)
    // Tant qu'une information manque, elle est surlignée et la page prévient le lecteur.
    expect(view.findAll('mark').length > 0).toBe(missing)
    expect(view.text().includes('en cours de finalisation')).toBe(missing)
  })
})
