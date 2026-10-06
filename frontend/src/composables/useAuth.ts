import type { Session } from '@supabase/supabase-js'
import { computed, ref } from 'vue'

import { supabase } from '../lib/supabase'

/** Mot de passe minimal imposé par le serveur d'authentification. */
export const MIN_PASSWORD_LENGTH = 12

const NOT_CONFIGURED = 'La création de compte n’est pas configurée sur cet environnement.'
const MESSAGES: Record<string, string> = {
  'Invalid login credentials': 'Adresse e-mail ou mot de passe incorrect.',
  'User already registered': 'Un compte existe déjà avec cette adresse : connectez-vous.',
  'Email not confirmed': 'Confirmez votre adresse via l’e-mail reçu, puis connectez-vous.',
  'Unsupported provider: provider is not enabled': 'La connexion Google n’est pas encore activée.',
}

// État partagé par toute l'application : une seule session à la fois.
const session = ref<Session | null>(null)
const ready = ref(false)
let initialised = false

function translate(message: string): string {
  return MESSAGES[message] ?? 'La connexion a échoué. Vérifiez vos informations et réessayez.'
}

function initialise(): void {
  if (initialised) return
  initialised = true
  if (!supabase) {
    ready.value = true
    return
  }
  void supabase.auth.getSession().then(({ data }) => {
    session.value = data.session
    ready.value = true
  })
  supabase.auth.onAuthStateChange((_event, next) => {
    session.value = next
  })
}

export type AuthOutcome = { ok: true; needsConfirmation: boolean } | { ok: false; message: string }

export function useAuth() {
  initialise()

  const user = computed(() => session.value?.user ?? null)
  const accessToken = computed(() => session.value?.access_token ?? null)
  const available = supabase !== null

  async function signUp(email: string, password: string): Promise<AuthOutcome> {
    if (!supabase) return { ok: false, message: NOT_CONFIGURED }
    const { data, error } = await supabase.auth.signUp({ email, password })
    if (error) return { ok: false, message: translate(error.message) }
    // Sans session immédiate, le serveur attend la confirmation de l'adresse e-mail.
    return { ok: true, needsConfirmation: data.session === null }
  }

  async function signIn(email: string, password: string): Promise<AuthOutcome> {
    if (!supabase) return { ok: false, message: NOT_CONFIGURED }
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) return { ok: false, message: translate(error.message) }
    return { ok: true, needsConfirmation: false }
  }

  /** Redirige vers Google ; au retour, l'utilisateur arrive sur `redirectTo`, connecté. */
  async function signInWithGoogle(redirectTo: string): Promise<AuthOutcome> {
    if (!supabase) return { ok: false, message: NOT_CONFIGURED }
    const { error } = await supabase.auth.signInWithOAuth({ provider: 'google', options: { redirectTo } })
    if (error) return { ok: false, message: translate(error.message) }
    return { ok: true, needsConfirmation: false }
  }

  async function signOut(): Promise<void> {
    await supabase?.auth.signOut()
  }

  return { user, accessToken, ready, available, signUp, signIn, signInWithGoogle, signOut }
}
