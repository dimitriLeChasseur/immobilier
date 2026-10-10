import type { SupabaseClient } from '@supabase/supabase-js'

import { API_URL } from '../api/audit'

// Supabase Auth est servi par le même domaine que l'API (route /auth/v1 du proxy).
const url = import.meta.env.VITE_SUPABASE_URL ?? API_URL
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

/** Faux si la clé publique n'est pas configurée : l'authentification est alors indisponible. */
export const AUTH_CONFIGURED = Boolean(anonKey)

let client: Promise<SupabaseClient | null> | undefined

/**
 * Client Supabase, ou null sans clé publique. La bibliothèque est chargée à part, après le
 * premier affichage : elle pèse autant que le reste de la page d'accueil.
 */
export function loadSupabase(): Promise<SupabaseClient | null> {
  if (!anonKey) return Promise.resolve(null)
  client ??= import('@supabase/supabase-js').then(({ createClient }) =>
    createClient(url, anonKey, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    }),
  )
  return client
}
