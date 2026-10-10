/**
 * Référencement, exécuté après « vite build » : accueil, tarifs, pages légales, liste et fiches
 * des communes écrits en HTML, plan du site, robots.txt et liste des communes.
 *
 * Une application monopage ne livre aux robots qu'une coquille vide. Chaque fiche communale
 * est donc aussi écrite en HTML dans dist/commune/<slug>/index.html, avec le même contenu
 * que la vue (src/lib/commune.ts) ; l'application la remplace ensuite à l'écran.
 *
 * Entrées : seo/communes.json (export « python -m app.seo », facultatif) et VITE_SITE_URL.
 */

import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  communePage,
  relatedCommunes,
  type CommuneLink,
  type CommunePage,
  type CommuneProfile,
} from '../src/lib/commune.ts'
import { LEGAL_INCOMPLETE } from '../src/lib/legal.ts'
import { renderPages, type RenderedPage } from './prerender.ts'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const DIST = join(ROOT, 'dist')
// Rendu des pages publiques, compilé par « vite build --ssr » et supprimé après usage.
const SSR_DIR = join(ROOT, 'dist-ssr')
const COMMUNES_FILE = join(ROOT, 'seo', 'communes.json')
// Les pages légales n'entrent au plan du site qu'une fois l'identité de l'éditeur complétée.
const LEGAL_PATHS = LEGAL_INCOMPLETE ? [] : ['/mentions-legales', '/cgv', '/confidentialite']
const STATIC_PATHS = ['/', '/tarifs', '/communes', ...LEGAL_PATHS]
// Pages de l'application sans contenu écrit : chacune reçoit son fichier, pour répondre 200 sans
// repli général, et part en noindex. La coquille sert aussi une adresse de commune inexistante :
// la fiche retire le noindex une fois la commune trouvée (src/views/CommuneView.vue).
// Pages écrites en HTML complet, avec leur contenu : celles que les moteurs doivent lire.
const PRERENDERED_PATHS = ['/', '/tarifs', '/communes', '/mentions-legales', '/cgv', '/confidentialite']
// Coquille vide de l'application, servie par la fonction des fiches communales non écrites.
const SHELL_PATH = '/app-shell'
const APP_PATHS = [SHELL_PATH, '/compte', '/mot-de-passe']

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

/** Variable de construction, lue dans l'environnement ou dans les fichiers .env. */
function buildVariable(name: string): string {
  const fromFiles = ['.env.production', '.env']
    .map((file) => join(ROOT, file))
    .filter((path) => existsSync(path))
    .flatMap((path) => readFileSync(path, 'utf8').split('\n'))
    .find((line) => line.startsWith(`${name}=`))
  const value = process.env[name] ?? fromFiles?.slice(name.length + 1) ?? ''
  return value.trim().replace(/\/+$/, '')
}

/** Adresse publique du site. */
function siteUrl(): string {
  return buildVariable('VITE_SITE_URL')
}

/**
 * Autorise l'API dans la politique de sécurité servie par Cloudflare Pages : le fichier
 * _headers porte un repère, remplacé ici par l'adresse réelle de l'API.
 */
function allowApiOrigin(): string {
  const path = join(DIST, '_headers')
  if (!existsSync(path)) return ''
  const api = buildVariable('VITE_API_URL')
  const origin = api ? new URL(api).origin : ''
  writeFileSync(path, readFileSync(path, 'utf8').replaceAll('__API_ORIGIN__', origin))
  return origin
}

function readCommunes(): CommuneProfile[] {
  if (!existsSync(COMMUNES_FILE)) return []
  const parsed: unknown = JSON.parse(readFileSync(COMMUNES_FILE, 'utf8'))
  return Array.isArray(parsed) ? (parsed as CommuneProfile[]) : []
}

function write(path: string, content: string): void {
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, content)
}

/** Contenu lisible sans JavaScript, remplacé par l'application à son démarrage. */
function staticBody(page: CommunePage, related: CommuneLink[], departement: string): string {
  const summary = page.summary.length
    ? `<section><h2>En bref</h2><ul>${page.summary.map((sentence) => `<li>${escapeHtml(sentence)}</li>`).join('')}</ul></section>`
    : ''
  const links = related
    .map((commune) => `<li><a href="/commune/${commune.slug}">${escapeHtml(commune.nom)}</a></li>`)
    .join('')
  const neighbours = links
    ? `<nav><h2>Autres communes du département ${escapeHtml(departement)}</h2><ul>${links}</ul></nav>`
    : ''
  const sections = page.sections
    .map((section) => {
      const facts = section.facts
        .map((fact) => {
          const note = fact.note ? `<dd>${escapeHtml(fact.note)}</dd>` : ''
          return `<dt>${escapeHtml(fact.label)}</dt><dd>${escapeHtml(fact.value)}</dd>${note}`
        })
        .join('')
      return `<section><h2>${escapeHtml(section.heading)}</h2><dl>${facts}</dl></section>`
    })
    .join('')
  return (
    `<main><p><a href="/communes">Communes</a></p><h1>${escapeHtml(page.heading)}</h1>` +
    `<p>${escapeHtml(page.intro)}</p>${summary}${sections}${neighbours}<p><a href="/">Auditer une adresse</a></p></main>`
  )
}

function replaceOnce(html: string, pattern: RegExp, replacement: string): string {
  if (!pattern.test(html)) throw new Error(`gabarit inattendu : ${pattern} introuvable dans dist/index.html`)
  return html.replace(pattern, () => replacement)
}

const ROBOTS_TAG = /<meta name="robots"[\s\S]*?\/>/
const NOINDEX_TAG = '<meta name="robots" content="noindex, follow" />'

interface Head {
  title: string
  description: string
  /** Chemin canonique de la page (« /tarifs »). */
  path: string
  noindex?: boolean
  /** Fil d'Ariane, de l'accueil à la page : libellé et chemin de chaque niveau. */
  breadcrumb?: [label: string, path: string][]
}

/** Fil d'Ariane en données structurées ; exige des adresses absolues, donc un domaine configuré. */
function breadcrumbScript(trail: [label: string, path: string][], base: string): string {
  const items = trail.map(([name, path], index) => ({
    '@type': 'ListItem',
    position: index + 1,
    name,
    item: `${base}${path}`,
  }))
  const data = { '@context': 'https://schema.org', '@type': 'BreadcrumbList', itemListElement: items }
  // « < » échappé : un nom de commune ne doit pas pouvoir fermer la balise.
  return `<script type="application/ld+json">${JSON.stringify(data).replace(/</g, '\\u003c')}</script>`
}

/** Gabarit de l'application avec les balises et le contenu d'une page. */
function pageHtml(template: string, head: Head, body: string, base: string): string {
  const url = `${base}${head.path}`
  const trail = base && head.breadcrumb ? breadcrumbScript(head.breadcrumb, base) : ''
  const canonical = base
    ? `<link rel="canonical" href="${escapeHtml(url)}" /><meta property="og:url" content="${escapeHtml(url)}" />${trail}`
    : ''
  let html = replaceOnce(template, /<title>[\s\S]*?<\/title>/, `<title>${escapeHtml(head.title)}</title>${canonical}`)
  if (head.noindex) html = replaceOnce(html, ROBOTS_TAG, NOINDEX_TAG)
  html = replaceOnce(
    html,
    /<meta\s+name="description"[\s\S]*?\/>/,
    `<meta name="description" content="${escapeHtml(head.description)}" />`,
  )
  html = replaceOnce(
    html,
    /<meta property="og:title"[\s\S]*?\/>/,
    `<meta property="og:title" content="${escapeHtml(head.title)}" />`,
  )
  html = replaceOnce(
    html,
    /<meta\s+property="og:description"[\s\S]*?\/>/,
    `<meta property="og:description" content="${escapeHtml(head.description)}" />`,
  )
  return replaceOnce(html, /<div id="app"><\/div>/, `<div id="app">${body}</div>`)
}

function communeHtml(template: string, profile: CommuneProfile, links: CommuneLink[], base: string): string {
  const page = communePage(profile)
  const path = `/commune/${profile.slug}`
  const head: Head = {
    title: page.title,
    description: page.description,
    path,
    breadcrumb: [
      ['Accueil', '/'],
      ['Communes', '/communes'],
      [profile.nom, path],
    ],
  }
  const body = staticBody(page, relatedCommunes(links, profile), profile.departement_nom || profile.departement_code)
  return pageHtml(template, head, body, base)
}

/** Fichier d'une page : « / » est index.html, « /tarifs » est tarifs.html. */
function pageFile(path: string): string {
  return join(DIST, path === '/' ? 'index.html' : `${path.slice(1)}.html`)
}

async function prerender(files: Record<string, string>): Promise<Map<string, RenderedPage>> {
  const bundle = join(SSR_DIR, 'prerender.js')
  if (!existsSync(bundle)) throw new Error('rendu des pages absent : lancez « npm run build »')
  const pages = await renderPages(bundle, PRERENDERED_PATHS, files)
  rmSync(SSR_DIR, { recursive: true })
  return pages
}

/** Page servie avec le code 404 ; l'application y affiche ensuite sa vue « introuvable ». */
function notFoundHtml(template: string): string {
  let html = replaceOnce(template, /<title>[\s\S]*?<\/title>/, '<title>Page introuvable | Audit Immobilier</title>')
  html = replaceOnce(html, ROBOTS_TAG, NOINDEX_TAG)
  return replaceOnce(
    html,
    /<div id="app"><\/div>/,
    '<div id="app"><main><h1>Page introuvable</h1><p><a href="/">Auditer une adresse</a></p></main></div>',
  )
}

function sitemap(base: string, communes: CommuneProfile[]): string {
  const paths = [...STATIC_PATHS, ...communes.map((commune) => `/commune/${commune.slug}`)]
  const urls = paths.map((path) => `<url><loc>${escapeHtml(`${base}${path}`)}</loc></url>`).join('')
  return `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls}</urlset>\n`
}

async function main(): Promise<void> {
  const communes = readCommunes()
  const base = siteUrl()
  // Vite laisse le repère tel quel quand la variable n'est pas définie (construction locale).
  const template = readFileSync(join(DIST, 'index.html'), 'utf8').replaceAll('%VITE_SITE_URL%', base)

  const communeLinks = communes.map(({ nom, slug, departement_code }) => ({ nom, slug, departement_code }))
  for (const commune of communes) {
    // Un fichier « <slug>.html » et non un dossier : l'adresse sans barre finale, celle du plan
    // du site et de la balise canonique, est alors servie directement, sans redirection.
    write(join(DIST, 'commune', `${commune.slug}.html`), communeHtml(template, commune, communeLinks, base))
  }
  const shell = replaceOnce(template, ROBOTS_TAG, NOINDEX_TAG)
  for (const path of APP_PATHS) write(pageFile(path), shell)
  // En dernier pour l'accueil : index.html, le gabarit, n'est remplacé qu'une fois tout écrit.
  const links = JSON.stringify(communeLinks)
  write(join(DIST, 'communes.json'), links)
  const pages = await prerender({ '/communes.json': links })
  write(join(DIST, '404.html'), notFoundHtml(template))
  for (const [path, page] of pages) {
    // Fenêtres de connexion, fermées : sans intérêt pour un moteur, l'application les recrée.
    const body = page.body.replace(/<dialog[\s\S]*?<\/dialog>/g, '')
    write(pageFile(path), pageHtml(template, { ...page, path }, body, base))
  }

  // Un plan du site exige des adresses absolues : sans domaine configuré, il n'est pas produit.
  // Le rapport d'une adresse (paramètre lat) contient des ventes DVF : exclu pour tous les
  // robots, y compris ceux qui n'exécutent pas le script posant la balise noindex.
  const robots = ['User-agent: *', 'Allow: /', 'Disallow: /*?lat=', 'Disallow: /*&lat=', 'Disallow: /compte', `Disallow: ${SHELL_PATH}`]
  if (base) {
    write(join(DIST, 'sitemap.xml'), sitemap(base, communes))
    robots.push(`Sitemap: ${base}/sitemap.xml`)
  }
  write(join(DIST, 'robots.txt'), `${robots.join('\n')}\n`)

  const plan = base ? 'plan du site écrit' : 'VITE_SITE_URL absent, plan du site non écrit'
  console.log(`Référencement : ${pages.size} page(s) de l'application, ${communes.length} page(s) commune, ${plan}.`)
  const origin = allowApiOrigin()
  console.log(origin ? `Politique de sécurité : API autorisée (${origin}).` : 'Politique de sécurité : VITE_API_URL absent.')
}

// Sortie explicite : le client d'authentification chargé par le rendu garde des minuteries.
main().then(
  () => process.exit(0),
  (error: unknown) => {
    console.error(error)
    process.exit(1)
  },
)
