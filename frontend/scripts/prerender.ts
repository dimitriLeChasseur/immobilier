/**
 * Exécute le rendu des pages publiques (src/prerender.ts, compilé par « vite build --ssr »).
 *
 * Les vues lisent l'adresse de la page et le stockage du navigateur dès leur création : un
 * faux navigateur (jsdom) leur est fourni le temps du rendu, et le réseau est coupé.
 */

import { pathToFileURL } from 'node:url'

import { JSDOM } from 'jsdom'

export interface RenderedPage {
  body: string
  title: string
  description: string
  noindex: boolean
}

interface Bundle {
  renderPage: (path: string) => Promise<RenderedPage>
}

const BROWSER_GLOBALS = ['window', 'document', 'location', 'history', 'navigator', 'localStorage', 'sessionStorage']

/**
 * `files` : fichiers du site que les pages demandent pendant leur rendu (« /communes.json »),
 * servis ici à la place du réseau.
 */
export async function renderPages(
  bundlePath: string,
  paths: string[],
  files: Record<string, string>,
): Promise<Map<string, RenderedPage>> {
  const dom = new JSDOM('<!doctype html><html><head></head><body></body></html>', { url: 'http://localhost/' })
  for (const name of BROWSER_GLOBALS) {
    // defineProperty : « navigator » est en lecture seule dans Node.
    Object.defineProperty(globalThis, name, { value: dom.window[name], configurable: true, writable: true })
  }
  // La navigation remet la page en haut : sans objet ici, et jsdom ne sait pas le faire.
  dom.window.scrollTo = () => undefined
  globalThis.fetch = (input) => {
    const content = files[String(input)]
    return Promise.resolve(content === undefined ? new Response('', { status: 404 }) : new Response(content))
  }
  const bundle = (await import(pathToFileURL(bundlePath).href)) as Bundle
  const pages = new Map<string, RenderedPage>()
  for (const path of paths) pages.set(path, await bundle.renderPage(path))
  return pages
}
