import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

import type { AuditStreamHandlers } from '../src/api/audit'
import { searchAddresses } from '../src/api/ban'
import { useAddressSearch } from '../src/composables/useAddressSearch'
import { DEFAULT_SOURCES, useAudit } from '../src/composables/useAudit'
import type { AddressSuggestion, SourceName, SourceResult } from '../src/types/audit'

/** Exécute un composable dans une portée réactive que le test peut arrêter. */
function inScope<T>(setup: () => T): { value: T; stop: () => void } {
  const scope = effectScope()
  const value = scope.run(setup)
  if (value === undefined) throw new Error('portée inactive')
  return { value, stop: () => scope.stop() }
}

const ANGERS: AddressSuggestion = { id: '49007', label: 'Angers', context: '49', lat: 47.47, lon: -0.55 }

describe('useAddressSearch', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('n’interroge le service qu’une fois la saisie stabilisée', async () => {
    const search = vi.fn().mockResolvedValue([ANGERS])
    const query = ref('')
    const { value: state, stop } = inScope(() => useAddressSearch(query, search))

    for (const value of ['ang', 'ange', 'anger']) {
      query.value = value
      await nextTick()
      await vi.advanceTimersByTimeAsync(100)
    }
    expect(search).not.toHaveBeenCalled()
    expect(state.loading.value).toBe(true)

    await vi.advanceTimersByTimeAsync(300)
    expect(search).toHaveBeenCalledTimes(1)
    expect(search.mock.calls[0]?.[0]).toBe('anger')
    expect(state.suggestions.value).toEqual([ANGERS])
    expect(state.loading.value).toBe(false)
    stop()
  })

  it('ignore une réponse arrivée après une nouvelle saisie', async () => {
    let resolveFirst: (value: AddressSuggestion[]) => void = () => undefined
    const search = vi
      .fn()
      .mockImplementationOnce(() => new Promise<AddressSuggestion[]>((resolve) => (resolveFirst = resolve)))
      .mockResolvedValue([ANGERS])
    const query = ref('')
    const { value: state, stop } = inScope(() => useAddressSearch(query, search))

    query.value = 'pari'
    await nextTick()
    await vi.advanceTimersByTimeAsync(300)
    query.value = 'angers'
    await nextTick()
    await vi.advanceTimersByTimeAsync(300)
    resolveFirst([{ ...ANGERS, id: 'obsolète', label: 'Paris' }])
    await vi.advanceTimersByTimeAsync(0)

    expect(state.suggestions.value).toEqual([ANGERS])
    stop()
  })

  it('vide les suggestions sous trois caractères et signale une panne', async () => {
    const search = vi.fn().mockRejectedValue(new Error('BAN 503'))
    const query = ref('')
    const { value: state, stop } = inScope(() => useAddressSearch(query, search))

    query.value = 'angers'
    await nextTick()
    await vi.advanceTimersByTimeAsync(300)
    expect(state.failed.value).toBe(true)

    query.value = 'an'
    await nextTick()
    expect(state.failed.value).toBe(false)
    expect(state.suggestions.value).toEqual([])
    stop()
  })
})

describe('searchAddresses', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('convertit les résultats BAN et écarte les entrées mal formées', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          features: [
            {
              geometry: { coordinates: [-0.55, 47.47] },
              properties: { id: '49007_1', label: '1 Rue X 49000 Angers', context: '49, Maine-et-Loire' },
            },
            { geometry: { coordinates: ['x', 'y'] }, properties: { id: 'bad', label: 'bad' } },
            { properties: {} },
          ],
        }),
    })
    vi.stubGlobal('fetch', fetchMock)

    expect(await searchAddresses('  1 rue x  ')).toEqual([
      { id: '49007_1', label: '1 Rue X 49000 Angers', context: '49, Maine-et-Loire', lat: 47.47, lon: -0.55 },
    ])
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('q=1+rue+x')
  })

  it('ne fait aucun appel pour une saisie trop courte', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    expect(await searchAddresses('an')).toEqual([])
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('useAudit', () => {
  function setup(names: SourceName[] = ['dvf', 'loyers']) {
    let handlers: AuditStreamHandlers | undefined
    const cancel = vi.fn()
    const open = vi.fn((_target, received: AuditStreamHandlers) => {
      handlers = received
      return cancel
    })
    const { value: audit, stop } = inScope(() => useAudit({ open, listSources: () => Promise.resolve(names) }))
    const current = (): AuditStreamHandlers => {
      if (!handlers) throw new Error('flux non ouvert')
      return handlers
    }
    return { audit, open, cancel, stop, handlers: current }
  }

  const TARGET = { lat: 47.47, lon: -0.55, banId: '49007' }
  const EMPTY: SourceResult = { status: 'empty', data: null, missing: [], error: null, duration_ms: 3 }

  it('remplit le rapport au fil des évènements', async () => {
    const { audit, handlers, stop } = setup()
    await Promise.resolve()
    expect(audit.sourceNames.value).toEqual(['dvf', 'loyers'])

    audit.start(TARGET)
    expect(audit.phase.value).toBe('loading')
    expect(audit.progress.value).toBe(0)

    handlers().onLocation({ ...TARGET, label: 'Angers', citycode: '49007', postcode: null, city: null, ban_id: '' })
    handlers().onSource('dvf', EMPTY)
    expect(audit.progress.value).toBe(0.5)
    expect(audit.location.value?.label).toBe('Angers')

    handlers().onSource('loyers', EMPTY)
    handlers().onDone({ generated_at: '2026-01-01T00:00:00Z', cached: false, is_partial: false, report_version: 1, duration_ms: 900 })
    expect(audit.phase.value).toBe('done')
    expect(audit.progress.value).toBe(1)
    stop()
  })

  it('annule le flux précédent quand un nouvel audit démarre ou que le composant disparaît', () => {
    const { audit, open, cancel, stop, handlers } = setup()
    audit.start(TARGET)
    handlers().onSource('dvf', EMPTY)
    audit.start({ ...TARGET, lat: 48 })

    expect(cancel).toHaveBeenCalledTimes(1)
    expect(open).toHaveBeenCalledTimes(2)
    expect(audit.sources.value).toEqual({})

    stop()
    expect(cancel).toHaveBeenCalledTimes(2)
  })

  it('expose le message d’erreur et garde la liste par défaut si le serveur ne la fournit pas', async () => {
    const open = vi.fn((_target, handlers: AuditStreamHandlers) => {
      handlers.onError('Hors couverture')
      return () => undefined
    })
    const { value: audit, stop } = inScope(() => useAudit({ open, listSources: () => Promise.reject(new Error('down')) }))
    await Promise.resolve()

    audit.start(TARGET)
    expect(audit.phase.value).toBe('error')
    expect(audit.errorMessage.value).toBe('Hors couverture')
    expect(audit.sourceNames.value).toEqual(DEFAULT_SOURCES)
    stop()
  })
})
