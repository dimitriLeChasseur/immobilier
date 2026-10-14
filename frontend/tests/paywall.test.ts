import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { computed, nextTick } from 'vue'

import { searchAddresses } from '../src/api/ban'
import LockedTeaser from '../src/components/LockedTeaser.vue'
import StickyUnlockBar from '../src/components/StickyUnlockBar.vue'
import SynthesisPanel from '../src/components/SynthesisPanel.vue'
import { nearbyCommunes, relatedCommunes } from '../src/lib/commune'
import { findingsCount, LOCKED, lockedGhost, lockedPromise } from '../src/lib/teaser'
import { UNLOCK_KEY } from '../src/lib/unlock'

const open = vi.fn()
const provide = { [UNLOCK_KEY as symbol]: { open, label: computed(() => 'Débloquer l’audit complet pour 2,99 €') } }

describe('cartes verrouillées', () => {
  it('annonce ce que chaque carte contient, sans en livrer le résultat', () => {
    expect(lockedPromise('bruit')).toBe('Bruit des routes et voies ferrées à l’adresse')
    expect(lockedPromise('batiment')).toContain('Année de construction')
    expect(lockedPromise('dvf')).toBe('Détail dans l’audit complet')
  })

  it('dessine une silhouette fixe et floutée, propre au type de carte', () => {
    expect(lockedGhost('dpe')).toBe('scale')
    expect(lockedGhost('bruit')).toBe('meter')
    expect(lockedGhost('georisques')).toBe('list')
    const scale = mount(LockedTeaser, {
      props: { hook: '42 diagnostics énergétiques analysés', promise: lockedPromise('dpe'), ghost: 'scale' },
      global: { provide },
    })
    const ghost = scale.find('.locked-blur')
    expect(ghost.attributes('aria-hidden')).toBe('true')
    // Les sept classes A à G, toujours les mêmes : rien n'y vient des données.
    expect(ghost.text().replace(/\s/g, '')).toBe('ABCDEFG')
    expect(scale.find('.locked-row').text()).toContain('Étiquette énergie la plus fréquente')
  })
})

describe('synthèse en aperçu', () => {
  it('compte les constats en toutes lettres', () => {
    expect(findingsCount(2, 1)).toBe('2 alertes et 1 point fort')
    expect(findingsCount(1, 3)).toBe('1 alerte et 3 points forts')
    expect(findingsCount(0, 2)).toBe('aucune alerte et 2 points forts')
    expect(findingsCount(3, 0)).toBe('3 alertes et aucun point fort')
  })

  it('titre sur ce qui a été trouvé, sans révéler les intitulés', () => {
    const panel = mount(SynthesisPanel, {
      props: {
        synthesis: {
          alertes: [
            { theme: 'Risques', titre: LOCKED, detail: LOCKED },
            { theme: 'Bruit', titre: LOCKED, detail: LOCKED },
          ],
          points_forts: [{ theme: 'Vie de quartier', titre: LOCKED, detail: LOCKED }],
        },
      },
      global: { provide },
    })
    expect(panel.find('h2').text()).toBe('Sur cette adresse : 2 alertes et 1 point fort')
    expect(panel.text()).not.toContain(LOCKED)
    // Barres masquées de longueurs différentes, pas une même mention répétée.
    const widths = panel.findAll('li p[aria-hidden="true"]').map((bar) => bar.classes().find((name) => name.startsWith('w-')))
    expect(new Set(widths).size).toBeGreaterThan(1)
  })
})

describe('barre de déblocage collante', () => {
  afterEach(() => vi.unstubAllGlobals())

  function observe() {
    const observers: { callback: IntersectionObserverCallback; disconnect: ReturnType<typeof vi.fn> }[] = []
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        disconnect = vi.fn()
        callback: IntersectionObserverCallback
        constructor(callback: IntersectionObserverCallback) {
          this.callback = callback
          observers.push(this)
        }
        observe(): void {}
      },
    )
    return (visible: boolean) =>
      observers[0]?.callback([{ isIntersecting: visible } as IntersectionObserverEntry], {} as IntersectionObserver)
  }

  it('n’apparaît qu’une fois le bouton principal sorti de l’écran', async () => {
    const setAnchorVisible = observe()
    const bar = mount(StickyUnlockBar, {
      props: { anchor: document.createElement('button'), summary: 'Sur cette adresse : 2 alertes et 1 point fort', label: 'Tout voir · 2,99 €' },
      global: { provide },
    })
    setAnchorVisible(true)
    await nextTick()
    expect(bar.find('[role="region"]').exists()).toBe(false)

    setAnchorVisible(false)
    await nextTick()
    expect(bar.text()).toContain('2 alertes et 1 point fort')
    await bar.find('button').trigger('click')
    expect(open).toHaveBeenCalled()
    bar.unmount()
  })
})

describe('fiches communales', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('limite la recherche d’adresse à la commune de la fiche', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ features: [] })))
    vi.stubGlobal('fetch', fetchMock)
    await searchAddresses('12 rue lenepveu', undefined, '49007')
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('citycode=49007')
  })

  it('propose les communes les plus proches, puis le reste du département sans doublon', () => {
    const angers = { slug: 'angers-49007', departement_code: '49', centre: [-0.55, 47.47] as [number, number] }
    const links = [
      { nom: 'Angers', slug: 'angers-49007', departement_code: '49', centre: [-0.55, 47.47] as [number, number] },
      { nom: 'Cholet', slug: 'cholet-49099', departement_code: '49', centre: [-0.88, 47.06] as [number, number] },
      { nom: 'Avrillé', slug: 'avrille-49015', departement_code: '49', centre: [-0.59, 47.5] as [number, number] },
      { nom: 'Laval', slug: 'laval-53130', departement_code: '53', centre: [-0.77, 48.07] as [number, number] },
      { nom: 'Saumur', slug: 'saumur-49328', departement_code: '49' },
    ]
    const nearby = nearbyCommunes(links, angers)
    expect(nearby.map((link) => link.nom)).toEqual(['Avrillé', 'Cholet', 'Laval'])
    expect(relatedCommunes(links, angers, nearby).map((link) => link.nom)).toEqual(['Saumur'])
    expect(nearbyCommunes(links, { ...angers, centre: null })).toEqual([])
  })
})
