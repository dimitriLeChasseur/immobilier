/**
 * Référencement, exécuté après « vite build » : pages statiques des communes, plan du site,
 * robots.txt et liste des communes.
 *
 * Une application monopage ne livre aux robots qu'une coquille vide. Chaque fiche communale
 * est donc aussi écrite en HTML dans dist/commune/<slug>/index.html, avec le même contenu
 * que la vue (src/lib/commune.ts) ; l'application la remplace ensuite à l'écran.
 *
 * Entrées : seo/communes.json (export « python -m app.seo », facultatif) et VITE_SITE_URL.
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { communePage, type CommunePage, type CommuneProfile } from '../src/lib/commune.ts'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const DIST = join(ROOT, 'dist')
const COMMUNES_FILE = join(ROOT, 'seo', 'communes.json')
const STATIC_PATHS = ['/', '/tarifs', '/communes']

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

/** Adresse publique du site, lue dans l'environnement ou dans les fichiers .env. */
function siteUrl(): string {
  const fromFiles = ['.env.production', '.env']
    .map((name) => join(ROOT, name))
    .filter((path) => existsSync(path))
    .flatMap((path) => readFileSync(path, 'utf8').split('\n'))
    .find((line) => line.startsWith('VITE_SITE_URL='))
  const value = process.env.VITE_SITE_URL ?? fromFiles?.slice('VITE_SITE_URL='.length) ?? ''
  return value.trim().replace(/\/+$/, '')
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

function communeHtml(template: string, profile: CommuneProfile, base: string): string {
  const page = communePage(profile)
  const canonical = base ? `<link rel="canonical" href="${base}/commune/${profile.slug}" />` : ''
  let html = replaceOnce(template, /<title>[\s\S]*?<\/title>/, `<title>${escapeHtml(page.title)}</title>${canonical}`)
  html = replaceOnce(
    html,
    /<meta\s+name="description"[\s\S]*?\/>/,
    `<meta name="description" content="${escapeHtml(page.description)}" />`,
  )
  html = replaceOnce(
    html,
    /<meta property="og:title"[\s\S]*?\/>/,
    `<meta property="og:title" content="${escapeHtml(page.title)}" />`,
  )
  html = replaceOnce(
    html,
    /<meta\s+property="og:description"[\s\S]*?\/>/,
    `<meta property="og:description" content="${escapeHtml(page.description)}" />`,
  )
  return replaceOnce(html, /<div id="app"><\/div>/, `<div id="app">${staticBody(page)}</div>`)
}

function sitemap(base: string, communes: CommuneProfile[]): string {
  const paths = [...STATIC_PATHS, ...communes.map((commune) => `/commune/${commune.slug}`)]
  const urls = paths.map((path) => `<url><loc>${escapeHtml(`${base}${path}`)}</loc></url>`).join('')
  return `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls}</urlset>\n`
}

function main(): void {
  const template = readFileSync(join(DIST, 'index.html'), 'utf8')
  const communes = readCommunes()
  const base = siteUrl()

  for (const commune of communes) {
    write(join(DIST, 'commune', commune.slug, 'index.html'), communeHtml(template, commune, base))
  }
  const links = communes.map(({ nom, slug, departement_code }) => ({ nom, slug, departement_code }))
  write(join(DIST, 'communes.json'), JSON.stringify(links))

  // Un plan du site exige des adresses absolues : sans domaine configuré, il n'est pas produit.
  // Le rapport d'une adresse (paramètre lat) contient des ventes DVF : exclu pour tous les
  // robots, y compris ceux qui n'exécutent pas le script posant la balise noindex.
  const robots = ['User-agent: *', 'Allow: /', 'Disallow: /*?lat=', 'Disallow: /*&lat=']
  if (base) {
    write(join(DIST, 'sitemap.xml'), sitemap(base, communes))
    robots.push(`Sitemap: ${base}/sitemap.xml`)
  }
  write(join(DIST, 'robots.txt'), `${robots.join('\n')}\n`)

  const plan = base ? 'plan du site écrit' : 'VITE_SITE_URL absent, plan du site non écrit'
  console.log(`Référencement : ${communes.length} page(s) commune, ${plan}.`)
}

main()
