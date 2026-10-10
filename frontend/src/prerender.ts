/**
 * Rendu en HTML des pages publiques, à la construction (scripts/prerender.ts).
 *
 * Une application monopage ne livre aux robots qu'une coquille vide : l'accueil, les tarifs,
 * la liste des communes et les pages légales sont donc aussi écrits en HTML, par les mêmes
 * composants que ceux affichés à l'écran.
 * L'application remplace ce rendu à son démarrage (src/main.ts).
 */
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'

import App from './App.vue'
import { DEFAULT_DESCRIPTION } from './lib/seo'
import { router } from './router'

export interface RenderedPage {
  body: string
  title: string
  description: string
  /** Vrai pour une page à ne pas indexer (page légale encore incomplète). */
  noindex: boolean
}

export async function renderPage(path: string): Promise<RenderedPage> {
  await router.push(path)
  await router.isReady()
  const { meta, name } = router.currentRoute.value
  if (name === 'not-found' || !meta.title) throw new Error(`page sans titre ou inconnue : ${path}`)
  const body = await renderToString(createSSRApp(App).use(router))
  return {
    body,
    title: meta.title,
    description: meta.description ?? DEFAULT_DESCRIPTION,
    noindex: meta.private === true,
  }
}
