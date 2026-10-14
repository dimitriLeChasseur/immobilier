import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

// Leaflet simulé : on vérifie les réglages passés à la carte, pas le rendu des tuiles.
const leaflet = vi.hoisted(() => {
  const layer = { addTo: () => layer, bindTooltip: () => layer, clearLayers: () => undefined }
  const map = { setView: vi.fn(), fitBounds: vi.fn(), invalidateSize: vi.fn(), remove: vi.fn() }
  return {
    map,
    options: [] as unknown[],
    browser: { mobile: false },
    layer,
  }
})

vi.mock('leaflet', () => ({
  default: {
    Browser: leaflet.browser,
    map: (_element: unknown, options: unknown) => {
      leaflet.options.push(options)
      return leaflet.map
    },
    tileLayer: () => leaflet.layer,
    layerGroup: () => leaflet.layer,
    circle: () => leaflet.layer,
    circleMarker: () => leaflet.layer,
    latLngBounds: () => ({}),
  },
}))
vi.mock('leaflet/dist/leaflet.css', () => ({}))

const { default: AuditMap } = await import('../src/components/AuditMap.vue')
const PROPS = { lat: 47.47, lon: -0.55, label: '10 Rue Saint-Aubin 49100 Angers' }

describe('carte de l’adresse', () => {
  afterEach(() => {
    leaflet.options.length = 0
    vi.unstubAllGlobals()
  })

  it('laisse un doigt faire défiler la page sur écran tactile', () => {
    leaflet.browser.mobile = true
    mount(AuditMap, { props: PROPS }).unmount()
    expect(leaflet.options[0]).toMatchObject({ scrollWheelZoom: false, dragging: false })
  })

  it('garde le glisser à la souris sur ordinateur', () => {
    leaflet.browser.mobile = false
    mount(AuditMap, { props: PROPS }).unmount()
    expect(leaflet.options[0]).toMatchObject({ dragging: true })
  })

  it('se recale quand son cadre change de taille, et cesse de l’observer une fois retirée', () => {
    const observers: { callback: () => void; disconnect: ReturnType<typeof vi.fn> }[] = []
    vi.stubGlobal(
      'ResizeObserver',
      class {
        disconnect = vi.fn()
        callback: () => void
        constructor(callback: () => void) {
          this.callback = callback
          observers.push(this)
        }
        observe(): void {}
      },
    )
    const wrapper = mount(AuditMap, { props: PROPS })
    observers[0]?.callback()
    expect(leaflet.map.invalidateSize).toHaveBeenCalled()
    wrapper.unmount()
    expect(observers[0]?.disconnect).toHaveBeenCalled()
    expect(leaflet.map.remove).toHaveBeenCalled()
  })
})
