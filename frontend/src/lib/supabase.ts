import { createClient, type SupabaseClient } from '@supabase/supabase-js'

import { API_URL } from '../api/audit'

// Supabase Auth est servi par le même domaine que l'API (route /auth/v1 du proxy).
const url = import.meta.env.VITE_SUPABASE_URL ?? API_URL
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

/** Client Supabase, ou null si la clé publique n'est pas configurée (authentification indisponible). */
export const supabase: SupabaseClient | null = anonKey
  ? createClient(url, anonKey, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    })
  : null
