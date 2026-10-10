// Cloudflare Pages Function, limitée aux fiches communales (voir _routes.json).
//
// Les 1 000 premières communes ont une page écrite à la construction, servie telle quelle.
// Les autres sont rendues par l'application à partir de l'API : pour elles, on renvoie la
// coquille vide de l'application (app-shell.html, sans le contenu de l'accueil) avec le code
// 200. Une adresse qui n'a pas la forme d'une fiche (« nom-49007 ») garde la réponse 404 du
// site, de même qu'un code qui ne désigne aucune commune : l'API le dit.
const COMMUNE_SLUG = /^[a-z0-9-]+-(\d{5}|2[ab]\d{3})$/
const NOT_FOUND = 404
// Au-delà, on sert la fiche sans attendre : l'application affichera elle-même l'erreur.
const API_TIMEOUT_MS = 3000

/** Faux seulement si l'API affirme que la commune n'existe pas ; un doute profite à la page. */
async function communeExists(apiUrl, code) {
  if (!apiUrl) return true
  try {
    const response = await fetch(`${apiUrl.replace(/\/+$/, '')}/api/v1/communes/${code}`, {
      signal: AbortSignal.timeout(API_TIMEOUT_MS),
    })
    return response.status !== NOT_FOUND
  } catch {
    return true
  }
}

export async function onRequestGet({ request, env, params }) {
  const asset = await env.ASSETS.fetch(request)
  const slug = String(params.slug)
  if (asset.status !== NOT_FOUND || !COMMUNE_SLUG.test(slug)) return asset
  const code = slug.split('-').pop().toUpperCase()
  if (!(await communeExists(env.VITE_API_URL, code))) return asset
  const shell = await env.ASSETS.fetch(new URL('/app-shell', request.url))
  return new Response(shell.body, { status: 200, headers: shell.headers })
}
