import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick } from 'vue'

import type { AuditStreamHandlers } from '../src/api/audit'
import HeroPreview from '../src/components/HeroPreview.vue'
import StatTile from '../src/components/StatTile.vue'
import { useAudit } from '../src/composables/useAudit'
import { easeOut, formatLike, splitNumber } from '../src/lib/countUp'
import type { SourceResult } from '../src/types/audit'

describe('compteur des chiffres clés', () => {
  it('retrouve le nombre d’une valeur mise en forme et la réécrit à l’identique', () => {
    const price = splitNumber('3 859 €/m²')
    expect(price).toMatchObject({ value: 3859, decimals: 0, group: ' ', after: ' €/m²' })
    expect(price && formatLike(price, 1234.4)).toBe('1 234 €/m²')
    expect(price && formatLike(price, 3859)).toBe('3 859 €/m²')

    const rate = splitNumber('6,2 %')
    expect(rate && formatLike(rate, 3.14159)).toBe('3,1 %')
    expect(splitNumber('—')).toBeNull()
    expect(easeOut(0)).toBe(0)
    expect(easeOut(1)).toBe(1)
  })

  afterEach(() => vi.unstubAllGlobals())

  function stubMotion(reduced: boolean) {
    let callback: IntersectionObserverCallback | undefined
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        constructor(received: IntersectionObserverCallback) {
          callback = received
        }
        observe(): void {}
        disconnect(): void {}
      },
    )
    vi.stubGlobal('matchMedia', () => ({ matches: reduced }))
    return () => callback?.([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver)
  }

  it('part de zéro et se pose sur la valeur exacte une fois la tuile à l’écran', async () => {
    vi.useFakeTimers()
    const enter = stubMotion(false)
    const tile = mount(StatTile, { props: { label: 'Prix médian', value: '3 859 €/m²', countUp: true } })
    const visible = () => tile.find('[aria-hidden="true"]').text()
    await nextTick()
    expect(visible()).toBe('0 €/m²')
    // Les lecteurs d'écran ont toujours la valeur finale.
    expect(tile.find('.sr-only').text()).toBe('3 859 €/m²')
    enter()
    await vi.advanceTimersByTimeAsync(1000)
    expect(visible()).toBe('3 859 €/m²')
    tile.unmount()
    vi.useRealTimers()
  })

  it('affiche directement la valeur si l’utilisateur limite les animations', () => {
    stubMotion(true)
    const tile = mount(StatTile, { props: { label: 'Prix médian', value: '3 859 €/m²', countUp: true } })
    expect(tile.find('[aria-hidden="true"]').text()).toBe('3 859 €/m²')
  })

  it('n’anime pas les tuiles qui ne le demandent pas, comme une année de construction', () => {
    stubMotion(false)
    const tile = mount(StatTile, { props: { label: 'Année de construction', value: '1975' } })
    expect(tile.text()).toBe('Année de construction1975')
  })
})

describe('apparition des cartes', () => {
  it('classe en rafale les sources arrivées ensemble, pas celles arrivées seules', () => {
    let now = 0
    vi.spyOn(performance, 'now').mockImplementation(() => now)
    let handlers: AuditStreamHandlers | undefined
    const scope = effectScope()
    const audit = scope.run(() =>
      useAudit({
        open: (_target, received) => {
          handlers = received
          return () => undefined
        },
        listSources: () => Promise.resolve([]),
      }),
    )
    const empty: SourceResult = { status: 'empty', data: null, missing: [], error: null, duration_ms: 1 }
    audit?.start({ lat: 47.47, lon: -0.55, banId: '' })
    // Rapport en cache : trois sources dans la même milliseconde, puis une, bien plus tard.
    handlers?.onSource('dvf', empty)
    handlers?.onSource('loyers', empty)
    handlers?.onSource('bruit', empty)
    now = 2000
    handlers?.onSource('dpe', empty)
    expect(audit?.arrivalRank.value).toEqual({ dvf: 0, loyers: 1, bruit: 2, dpe: 0 })
    scope.stop()
    vi.restoreAllMocks()
  })
})

describe('maquette de l’accueil', () => {
  it('mène au rapport d’exemple et ne montre aucun chiffre inventé', async () => {
    const hero = mount(HeroPreview)
    const button = hero.find('button')
    expect(button.attributes('aria-label')).toBe('Voir un rapport d’exemple complet')
    // Illustration seulement : ni prix, ni décompte, ni adresse réelle.
    expect(hero.text()).not.toMatch(/\d/)
    expect(hero.text()).toContain('Illustration')
    await button.trigger('click')
    await nextTick()
    expect(hero.emitted('demo')).toHaveLength(1)
  })
})
