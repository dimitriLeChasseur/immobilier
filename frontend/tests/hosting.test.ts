import { describe, expect, it } from 'vitest'

// @ts-expect-error fonction d'hébergement en JavaScript, sans déclaration de types
import { onRequestGet } from '../functions/commune/[slug].js'

/** Hébergeur simulé : seules les adresses listées ont un fichier. */
function hosting(files: Record<string, string>) {
  return {
    ASSETS: {
      fetch: (input: Request | URL) => {
        const path = new URL(input instanceof Request ? input.url : input).pathname
        const body = files[path]
        return Promise.resolve(new Response(body ?? 'introuvable', { status: body === undefined ? 404 : 200 }))
      },
    },
  }
}

async function get(path: string): Promise<[number, string]> {
  const env = hosting({ '/': 'application', '/commune/angers-49007': 'fiche statique' })
  const response: Response = await onRequestGet({
    request: new Request(`https://exemple.test${path}`),
    env,
    params: { slug: path.split('/').pop() },
  })
  return [response.status, await response.text()]
}

describe('fiches communales côté hébergeur', () => {
  it('sert telle quelle une fiche écrite à la construction', async () => {
    expect(await get('/commune/angers-49007')).toEqual([200, 'fiche statique'])
  })

  it('rend par l’application une commune sans fiche statique', async () => {
    expect(await get('/commune/embrun-05046')).toEqual([200, 'application'])
    expect(await get('/commune/ajaccio-2a004')).toEqual([200, 'application'])
  })

  it('laisse en 404 une adresse qui n’a pas la forme d’une fiche', async () => {
    expect(await get('/commune/nimporte')).toEqual([404, 'introuvable'])
    expect(await get('/commune/angers-4900')).toEqual([404, 'introuvable'])
  })
})
