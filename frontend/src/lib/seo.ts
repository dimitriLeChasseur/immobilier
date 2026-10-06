/** Balises de référencement mises à jour à chaque changement de page. */

export interface PageMeta {
  title: string
  description: string
  /** Chemin canonique de la page, sans paramètres (« /tarifs »). */
  path: string
  /** Vrai pour une page à ne pas indexer (résultat d'audit d'une adresse). */
  noindex?: boolean
}

export const SITE_NAME = 'Audit Immobilier'
export const DEFAULT_DESCRIPTION =
  'Audit immobilier d’une adresse en quelques secondes : prix des ventes voisines, risques, bâtiment, urbanisme, ' +
  'écoles et quartier, à partir des données publiques.'

function siteUrl(): string {
  const configured = import.meta.env.VITE_SITE_URL
  return (configured && configured.length > 0 ? configured : window.location.origin).replace(/\/+$/, '')
}

function upsert(selector: string, create: () => HTMLElement, apply: (element: HTMLElement) => void): void {
  let element = document.head.querySelector<HTMLElement>(selector)
  if (!element) {
    element = create()
    document.head.appendChild(element)
  }
  apply(element)
}

function setMeta(attribute: 'name' | 'property', key: string, content: string): void {
  upsert(
    `meta[${attribute}="${key}"]`,
    () => {
      const meta = document.createElement('meta')
      meta.setAttribute(attribute, key)
      return meta
    },
    (meta) => meta.setAttribute('content', content),
  )
}

export function setPageMeta(meta: PageMeta): void {
  const url = `${siteUrl()}${meta.path}`
  document.title = meta.title
  setMeta('name', 'description', meta.description)
  setMeta('name', 'robots', meta.noindex ? 'noindex, follow' : 'index, follow')
  setMeta('property', 'og:title', meta.title)
  setMeta('property', 'og:description', meta.description)
  setMeta('property', 'og:url', url)
  upsert(
    'link[rel="canonical"]',
    () => {
      const link = document.createElement('link')
      link.setAttribute('rel', 'canonical')
      return link
    },
    (link) => link.setAttribute('href', url),
  )
}
