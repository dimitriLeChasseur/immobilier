import type { ComputedRef, InjectionKey } from 'vue'

/** Action « débloquer l'audit », fournie par la vue d'audit aux cartes verrouillées. */
export interface UnlockAction {
  open: () => void
  /** Libellé du bouton : création de compte pour un visiteur, paiement pour un utilisateur connecté. */
  label: ComputedRef<string>
}

export const UNLOCK_KEY: InjectionKey<UnlockAction> = Symbol('unlock')
