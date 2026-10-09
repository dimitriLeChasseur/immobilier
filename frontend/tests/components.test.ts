import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { h } from 'vue'

import RisksCard from '../src/components/cards/RisksCard.vue'
import type { YieldLine } from '../src/lib/yield'
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

const FLATS: YieldLine[] = [
  { id: 'appartement', label: 'Appartement, toutes tailles', rentPerM2: 14, pricePerM2: 4200, sales: 40, gross: 4 },
]

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
    expect(text).toContain('Commune concernée par un atlas des zones inondables (La Loire)')
    expect(text).toContain('Exposition moyenne')
    expect(text).toContain('Sol sensible : recherchez des fissures')
    expect(text).toContain('Zone 2 - faible')
    expect(text).toContain('Non renseigné')
  })
})

const NO_EXTRAS = { surface: 50, condoChargesEstimate: null, propertyTaxRate: null }

describe('YieldCard', () => {
  it('calcule le rendement quand prix et loyer sont connus', () => {
    const card = mount(YieldCard, { props: { ...NO_EXTRAS, loading: false, lines: FLATS } })
    expect(card.text()).toContain('4,0 %')
  })

  it('suit la surface saisie pour choisir le type d’appartement, sauf choix explicite', async () => {
    const lines: YieldLine[] = [
      ...FLATS,
      { id: 't1_t2', label: 'Appartement de 1 ou 2 pièces', rentPerM2: 17, pricePerM2: 4000, sales: 12, gross: 5.1 },
      { id: 't3_plus', label: 'Appartement de 3 pièces et plus', rentPerM2: 12, pricePerM2: 4500, sales: 9, gross: 3.2 },
    ]
    const card = mount(YieldCard, { props: { ...NO_EXTRAS, loading: false, lines, surface: 30 } })
    expect(card.text()).toContain('Rendement brut5,1 %')
    await card.setProps({ surface: 80 })
    expect(card.text()).toContain('Rendement brut3,2 %')
    await card.find('select').setValue('appartement')
    expect(card.text()).toContain('Rendement brut4,0 %')
    // Net hors charges : loyer et prix du type choisi, pour la surface saisie.
    expect(card.text().replace(/\s/g, ' ')).toContain('loyers 13 440')
  })

  it('reste en attente puis explique l’absence de calcul', () => {
    const pending = mount(YieldCard, { props: { ...NO_EXTRAS, loading: true, lines: [] } })
    expect(pending.find('output').exists()).toBe(true)
    const missing = mount(YieldCard, { props: { ...NO_EXTRAS, loading: false, lines: [] } })
    expect(missing.text()).toContain('Calcul impossible')
  })
})
