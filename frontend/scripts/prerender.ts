/**
 * Exécute le rendu des pages publiques (src/prerender.ts, compilé par « vite build --ssr »).
 *
 * Les vues lisent l'adresse de la page et le stockage du navigateur dès leur création : un
 * faux navigateur (jsdom) leur est fourni le temps du rendu.
 */

import { pathToFileURL } from 'node:url'

import { JSDOM } from 'jsdom'

export interface RenderedPage {
  body: string
  title: string
  description: string
}

interface Bundle {
  renderPage: (path: string) => Promise<RenderedPage>
}

const BROWSER_GLOBALS = ['window', 'document', 'location', 'history', 'navigator', 'localStorage', 'sessionStorage']

export async function renderPages(bundlePath: string, paths: string[]): Promise<Map<string, RenderedPage>> {
  const dom = new JSDOM('<!doctype html><html><head></head><body></body></html>', { url: 'http://localhost/' })
  for (const name of BROWSER_GLOBALS) {
    // defineProperty : « navigator » est en lecture seule dans Node.
    Object.defineProperty(globalThis, name, { value: dom.window[name], configurable: true, writable: true })
  }
  // La navigation remet la page en haut : sans objet ici, et jsdom ne sait pas le faire.
  dom.window.scrollTo = () => undefined
  const bundle = (await import(pathToFileURL(bundlePath).href)) as Bundle
  const pages = new Map<string, RenderedPage>()
  for (const path of paths) pages.set(path, await bundle.renderPage(path))
  return pages
}
