/**
 * Défi anti-robot Cloudflare Turnstile, sans cookie ni énigme à résoudre.
 *
 * Inactif tant que VITE_TURNSTILE_SITE_KEY n'est pas définie : le serveur d'authentification
 * doit alors, lui aussi, ne pas l'exiger (CAPTCHA_ENABLED=false).
 */

export const CAPTCHA_SITE_KEY: string | undefined = import.meta.env.VITE_TURNSTILE_SITE_KEY || undefined

const SCRIPT_URL = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'

export interface TurnstileApi {
  render: (
    container: HTMLElement,
    options: {
      sitekey: string
      language: string
      callback: (token: string) => void
      'expired-callback': () => void
      'error-callback': () => void
    },
  ) => string
  reset: (widgetId: string) => void
  remove: (widgetId: string) => void
}

declare global {
  interface Window {
    turnstile?: TurnstileApi
  }
}

let loading: Promise<TurnstileApi> | null = null

/** Charge le script une seule fois, à la première ouverture d'un formulaire protégé. */
export function loadCaptcha(): Promise<TurnstileApi> {
  loading ??= new Promise<TurnstileApi>((resolve, reject) => {
    if (window.turnstile) {
      resolve(window.turnstile)
      return
    }
    const script = document.createElement('script')
    script.src = SCRIPT_URL
    script.async = true
    script.onload = () => (window.turnstile ? resolve(window.turnstile) : reject(new Error('turnstile')))
    script.onerror = () => {
      loading = null
      reject(new Error('turnstile'))
    }
    document.head.append(script)
  })
  return loading
}
