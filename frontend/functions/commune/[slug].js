// Cloudflare Pages Function, limitée aux fiches communales (voir _routes.json).
//
// Les 1 000 premières communes ont une page écrite à la construction, servie telle quelle.
// Les autres sont rendues par l'application à partir de l'API : pour elles, on renvoie la
// page de l'application avec le code 200. Une adresse qui n'a pas la forme d'une fiche
// (« nom-49007 ») garde la réponse 404 du site.
const COMMUNE_SLUG = /^[a-z0-9-]+-(\d{5}|2[ab]\d{3})$/

export async function onRequestGet({ request, env, params }) {
  const asset = await env.ASSETS.fetch(request)
  if (asset.status !== 404 || !COMMUNE_SLUG.test(String(params.slug))) return asset
  const shell = await env.ASSETS.fetch(new URL('/', request.url))
  return new Response(shell.body, { status: 200, headers: shell.headers })
}
