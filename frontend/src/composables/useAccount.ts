import { ref, watch } from 'vue'

import { fetchAccount, type Account } from '../api/billing'
import { useAuth } from './useAuth'

// État partagé : crédits et abonnement de l'utilisateur connecté.
const account = ref<Account | null>(null)
let watching = false

export function useAccount() {
  const { accessToken, user } = useAuth()

  async function refresh(): Promise<void> {
    const token = accessToken.value
    if (!token) {
      account.value = null
      return
    }
    try {
      account.value = await fetchAccount(token)
    } catch {
      // Compte indisponible : l'interface se comporte comme sans crédit ni abonnement.
      account.value = null
    }
  }

  if (!watching) {
    watching = true
    watch(() => user.value?.id, () => void refresh(), { immediate: true })
  }

  return { account, refresh }
}
