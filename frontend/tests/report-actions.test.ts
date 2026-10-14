import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

import type { AuditPhase } from '../src/composables/useAudit'
import { usePaymentReturn } from '../src/composables/usePaymentReturn'
import { usePdfExport } from '../src/composables/usePdfExport'
import { readPendingAudit, savePendingAudit } from '../src/lib/pending'
import type { AuditLocation, ReportMeta, SourceResults } from '../src/types/audit'

const pdf = vi.hoisted(() => ({ save: vi.fn(), fail: false }))
vi.mock('../src/lib/pdf', () => ({
  buildReportPdf: () => {
    if (pdf.fail) throw new Error('canvas')
    return { save: pdf.save }
  },
  collectCharts: () => [],
  reportFileName: () => 'audit.pdf',
}))

function inScope<T>(setup: () => T): { value: T; stop: () => void } {
  const scope = effectScope()
  const value = scope.run(setup)
  if (value === undefined) throw new Error('portée inactive')
  return { value, stop: () => scope.stop() }
}

const ADDRESS = { lat: 47.47, lon: -0.55, banId: '49007_1', label: '1 Rue X 49000 Angers' }

describe('retour de la page de paiement', () => {
  afterEach(() => {
    vi.useRealTimers()
    localStorage.clear()
  })

  it('relance l’audit tant que Stripe n’a pas confirmé, puis avoue le retard', async () => {
    vi.useFakeTimers()
    const phase = ref<AuditPhase>('loading')
    const retry = vi.fn(() => {
      phase.value = 'loading'
    })
    const { value, stop } = inScope(() => usePaymentReturn(phase, ref(true), retry, '?paiement=ok'))
    expect(value.paid.value).toBe(true)

    for (let attempt = 1; attempt <= 6; attempt += 1) {
      phase.value = 'done'
      await nextTick()
      await vi.advanceTimersByTimeAsync(2500)
      expect(retry).toHaveBeenCalledTimes(attempt)
    }
    expect(value.late.value).toBe(true)
    phase.value = 'done'
    await nextTick()
    await vi.advanceTimersByTimeAsync(2500)
    expect(retry).toHaveBeenCalledTimes(6)
    stop()
  })

  it('oublie l’adresse mémorisée dès que le rapport complet arrive', async () => {
    savePendingAudit(ADDRESS)
    const phase = ref<AuditPhase>('loading')
    const { value, stop } = inScope(() => usePaymentReturn(phase, ref(false), vi.fn(), '?paiement=ok'))
    phase.value = 'done'
    await nextTick()
    expect(value.paid.value).toBe(false)
    expect(readPendingAudit()).toBeNull()
    stop()
  })

  it('n’attend rien sans retour de paiement, et coupe sa relance si la page est quittée', async () => {
    vi.useFakeTimers()
    const phase = ref<AuditPhase>('loading')
    const retry = vi.fn()
    const quiet = inScope(() => usePaymentReturn(phase, ref(true), retry, ''))
    phase.value = 'done'
    await nextTick()
    await vi.advanceTimersByTimeAsync(2500)
    expect(retry).not.toHaveBeenCalled()
    quiet.stop()

    const phase2 = ref<AuditPhase>('loading')
    const left = inScope(() => usePaymentReturn(phase2, ref(true), retry, '?paiement=ok'))
    phase2.value = 'done'
    await nextTick()
    left.stop()
    await vi.advanceTimersByTimeAsync(2500)
    expect(retry).not.toHaveBeenCalled()
  })
})

describe('export PDF', () => {
  const location: AuditLocation = { lat: 47.47, lon: -0.55, label: 'Angers', citycode: '49007', postcode: null, city: null, ban_id: '' }

  function setup(locked: boolean) {
    return inScope(() =>
      usePdfExport(
        {
          location: ref(location),
          meta: ref<ReportMeta | null>(null),
          sources: ref<SourceResults>({}),
          checkedItems: ref<string[]>([]),
        },
        ref(locked),
      ),
    )
  }

  afterEach(() => {
    pdf.save.mockClear()
    pdf.fail = false
  })

  it('n’exporte jamais un aperçu, dont les valeurs sont masquées', async () => {
    const { value, stop } = setup(true)
    await value.exportPdf()
    expect(pdf.save).not.toHaveBeenCalled()
    stop()
  })

  it('enregistre le PDF du rapport complet', async () => {
    const { value, stop } = setup(false)
    await value.exportPdf()
    expect(pdf.save).toHaveBeenCalledWith('audit.pdf')
    expect(value.exporting.value).toBe(false)
    expect(value.exportFailed.value).toBe(false)
    stop()
  })

  it('signale un échec sans rester bloqué en préparation', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    pdf.fail = true
    const { value, stop } = setup(false)
    await value.exportPdf()
    expect(value.exportFailed.value).toBe(true)
    expect(value.exporting.value).toBe(false)
    stop()
  })
})
