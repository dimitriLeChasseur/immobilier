import { onScopeDispose, ref, watch, type Ref } from 'vue'

import { MIN_QUERY_LENGTH, searchAddresses } from '../api/ban'
import type { AddressSuggestion } from '../types/audit'

const DEBOUNCE_MS = 250

type Search = (query: string, signal?: AbortSignal) => Promise<AddressSuggestion[]>

/**
 * Autocomplétion avec temporisation : seule la dernière saisie produit un résultat,
 * les requêtes devenues obsolètes sont annulées.
 */
export function useAddressSearch(query: Ref<string>, search: Search = searchAddresses) {
  const suggestions = ref<AddressSuggestion[]>([])
  const loading = ref(false)
  const failed = ref(false)

  let timer: ReturnType<typeof setTimeout> | undefined
  let controller: AbortController | undefined

  function cancelPending(): void {
    clearTimeout(timer)
    controller?.abort()
  }

  function clear(): void {
    cancelPending()
    suggestions.value = []
    loading.value = false
    failed.value = false
  }

  async function run(value: string): Promise<void> {
    controller = new AbortController()
    const { signal } = controller
    try {
      const results = await search(value, signal)
      if (signal.aborted) return
      suggestions.value = results
      failed.value = false
    } catch {
      if (signal.aborted) return
      suggestions.value = []
      failed.value = true
    }
    loading.value = false
  }

  watch(query, (value) => {
    cancelPending()
    if (value.trim().length < MIN_QUERY_LENGTH) {
      clear()
      return
    }
    loading.value = true
    timer = setTimeout(() => void run(value), DEBOUNCE_MS)
  })

  onScopeDispose(cancelPending)

  return { suggestions, loading, failed, clear }
}
