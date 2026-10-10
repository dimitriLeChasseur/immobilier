/**
 * Référencement, exécuté après « vite build » : pages de l'accueil, des tarifs et des communes
 * écrites en HTML, plan du site, robots.txt et liste des communes.
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

import { communePage, type CommunePage, type CommuneProfile } from '../src/lib/commune.ts'
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
// Pages de l'application : chacune reçoit son fichier, pour répondre 200 sans repli général.
// Pages écrites en HTML complet, avec leur contenu : celles que les moteurs doivent lire.
const PRERENDERED_PATHS = ['/', '/tarifs']
// Coquille vide de l'application, servie par la fonction des fiches communales non écrites.
const SHELL_PATH = '/app-shell'
const APP_PATHS = [SHELL_PATH, '/communes', '/compte', '/mot-de-passe', '/mentions-legales', '/cgv', '/confidentialite']

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
function staticBody(page: CommunePage): string {
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
    `<p>${escapeHtml(page.intro)}</p>${sections}<p><a href="/">Auditer une adresse</a></p></main>`
  )
}

function replaceOnce(html: string, pattern: RegExp, replacement: string): string {
  if (!pattern.test(html)) throw new Error(`gabarit inattendu : ${pattern} introuvable dans dist/index.html`)
  return html.replace(pattern, () => replacement)
}

interface Head {
  title: string
  description: string
  /** Chemin canonique de la page (« /tarifs »). */
  path: string
}

/** Gabarit de l'application avec les balises et le contenu d'une page. */
function pageHtml(template: string, head: Head, body: string, base: string): string {
  const url = `${base}${head.path}`
  const canonical = base
    ? `<link rel="canonical" href="${escapeHtml(url)}" /><meta property="og:url" content="${escapeHtml(url)}" />`
    : ''
  let html = replaceOnce(template, /<title>[\s\S]*?<\/title>/, `<title>${escapeHtml(head.title)}</title>${canonical}`)
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

function communeHtml(template: string, profile: CommuneProfile, base: string): string {
  const page = communePage(profile)
  const head = { title: page.title, description: page.description, path: `/commune/${profile.slug}` }
  return pageHtml(template, head, staticBody(page), base)
}

/** Fichier d'une page : « / » est index.html, « /tarifs » est tarifs.html. */
function pageFile(path: string): string {
  return join(DIST, path === '/' ? 'index.html' : `${path.slice(1)}.html`)
}

async function prerender(): Promise<Map<string, RenderedPage>> {
  const bundle = join(SSR_DIR, 'prerender.js')
  if (!existsSync(bundle)) throw new Error('rendu des pages absent : lancez « npm run build »')
  const pages = await renderPages(bundle, PRERENDERED_PATHS)
  rmSync(SSR_DIR, { recursive: true })
  return pages
}

/** Page servie avec le code 404 ; l'application y affiche ensuite sa vue « introuvable ». */
function notFoundHtml(template: string): string {
  let html = replaceOnce(template, /<title>[\s\S]*?<\/title>/, '<title>Page introuvable | Audit Immobilier</title>')
  html = replaceOnce(html, /<meta name="robots"[\s\S]*?\/>/, '<meta name="robots" content="noindex, follow" />')
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
  const template = readFileSync(join(DIST, 'index.html'), 'utf8')
  const communes = readCommunes()
  const base = siteUrl()

  for (const commune of communes) {
    // Un fichier « <slug>.html » et non un dossier : l'adresse sans barre finale, celle du plan
    // du site et de la balise canonique, est alors servie directement, sans redirection.
    write(join(DIST, 'commune', `${commune.slug}.html`), communeHtml(template, commune, base))
  }
  for (const path of APP_PATHS) write(pageFile(path), template)
  // En dernier pour l'accueil : index.html, le gabarit, n'est remplacé qu'une fois tout écrit.
  const pages = await prerender()
  write(join(DIST, '404.html'), notFoundHtml(template))
  for (const [path, page] of pages) {
    // Fenêtres de connexion, fermées : sans intérêt pour un moteur, l'application les recrée.
    const body = page.body.replace(/<dialog[\s\S]*?<\/dialog>/g, '')
    write(pageFile(path), pageHtml(template, { ...page, path }, body, base))
  }
  const links = communes.map(({ nom, slug, departement_code }) => ({ nom, slug, departement_code }))
  write(join(DIST, 'communes.json'), JSON.stringify(links))

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
