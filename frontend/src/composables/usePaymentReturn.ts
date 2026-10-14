import { computed, onScopeDispose, ref, watch, type Ref } from 'vue'

import { clearPendingAudit } from '../lib/pending'
import type { AuditPhase } from './useAudit'

// Retour de la page de paiement : Stripe confirme l'achat au serveur en quelques secondes.
const PAYMENT_CHECKS = 6
const PAYMENT_CHECK_DELAY_MS = 2500

/**
 * Après un paiement, redemande le rapport tant que la confirmation de Stripe n'est pas arrivée.
 * `locked` est vrai tant que le serveur renvoie l'aperçu ; `retry` relance l'audit.
 */
export function usePaymentReturn(
  phase: Ref<AuditPhase>,
  locked: Ref<boolean>,
  retry: () => void,
  search = window.location.search,
) {
  const paid = ref(new URLSearchParams(search).get('paiement') === 'ok')
  const checks = ref(0)
  let timer: ReturnType<typeof setTimeout> | undefined

  // Toutes les relances ont été faites sans confirmation : l'utilisateur est invité à patienter.
  const late = computed(() => checks.value >= PAYMENT_CHECKS)

  watch(phase, (current) => {
    if (current !== 'done') return
    if (!locked.value) {
      paid.value = false
      clearPendingAudit()
    } else if (paid.value && checks.value < PAYMENT_CHECKS) {
      checks.value += 1
      timer = setTimeout(retry, PAYMENT_CHECK_DELAY_MS)
    }
  })

  onScopeDispose(() => clearTimeout(timer))

  return { paid, late }
}
