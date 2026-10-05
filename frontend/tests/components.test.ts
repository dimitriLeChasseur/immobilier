import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { h } from 'vue'

import RisksCard from '../src/components/cards/RisksCard.vue'
import YieldCard from '../src/components/cards/YieldCard.vue'
import SourceCard from '../src/components/SourceCard.vue'
import type { SourceResult } from '../src/types/audit'

const base = { title: 'Loyers', emptyText: 'Rien pour cette commune.' }
const slots = {
  default: ({ data }: { data: unknown }) => h('p', `valeur ${(data as { valeur: number }).valeur}`),
}

function result(overrides: Partial<SourceResult<{ valeur: number }>>): SourceResult<{ valeur: number }> {
  return { status: 'ok', data: { valeur: 7 }, missing: [], error: null, duration_ms: 1, ...overrides }
}

describe('SourceCard', () => {
  it('affiche un squelette tant que la source n’a pas répondu', () => {
    const card = mount(SourceCard, { props: base, slots })
    expect(card.find('output').exists()).toBe(true)
    expect(card.attributes('aria-busy')).toBe('true')
    expect(card.text()).not.toContain('valeur')
  })

  it('affiche les données reçues', () => {
    const card = mount(SourceCard, { props: { ...base, result: result({}) }, slots })
    expect(card.text()).toContain('valeur 7')
    expect(card.find('output').exists()).toBe(false)
  })

  it('signale une réponse partielle sans masquer les données', () => {
    const card = mount(SourceCard, { props: { ...base, result: result({ status: 'partial', missing: ['seveso'] }) }, slots })
    expect(card.text()).toContain('Partiel')
    expect(card.text()).toContain('valeur 7')
  })

  it('explique une source vide ou en échec', () => {
    const empty = mount(SourceCard, { props: { ...base, result: result({ status: 'empty', data: null }) }, slots })
    expect(empty.text()).toContain('Rien pour cette commune.')

    const timeout = mount(SourceCard, {
      props: { ...base, result: result({ status: 'timeout', data: null, error: 'La source n’a pas répondu.' }) },
      slots,
    })
    expect(timeout.text()).toContain('Délai dépassé')
    expect(timeout.text()).toContain('La source n’a pas répondu.')
  })
})

describe('RisksCard', () => {
  it('traduit les niveaux en verdicts lisibles et affiche les recommandations reçues', () => {
    const card = mount(RisksCard, {
      props: {
        data: {
          inondation: { concerne: true, atlas_zones_inondables: ['La Loire'] },
          argiles: { code: '2', exposition: 'Exposition moyenne' },
          sismicite: { code: '2', zone: '2 - FAIBLE' },
          radon: null,
          recommandations: { argiles: 'Sol sensible : recherchez des fissures sur les façades.' },
        },
      },
    })
    const text = card.text()
    expect(text).toContain('Zone inondable (La Loire)')
    expect(text).toContain('Exposition moyenne')
    expect(text).toContain('Sol sensible : recherchez des fissures')
    expect(text).toContain('Zone 2 - faible')
    expect(text).toContain('Non renseigné')
  })
})

const NO_EXTRAS = { surface: 50, condoChargesEstimate: null, propertyTaxRate: null }

describe('YieldCard', () => {
  it('calcule le rendement quand prix et loyer sont connus', () => {
    const card = mount(YieldCard, { props: { ...NO_EXTRAS, loading: false, rentPerM2: 14, pricePerM2: 4200 } })
    expect(card.text()).toContain('4,0 %')
  })

  it('reste en attente puis explique l’absence de calcul', () => {
    const pending = mount(YieldCard, { props: { ...NO_EXTRAS, loading: true, rentPerM2: null, pricePerM2: 4200 } })
    expect(pending.find('output').exists()).toBe(true)
    const missing = mount(YieldCard, { props: { ...NO_EXTRAS, loading: false, rentPerM2: null, pricePerM2: 4200 } })
    expect(missing.text()).toContain('Calcul impossible')
  })
})
