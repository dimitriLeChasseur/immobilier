import { afterEach, describe, expect, it, vi } from 'vitest'

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

async function get(path: string, apiUrl?: string): Promise<[number, string]> {
  const files = { '/': 'accueil', '/app-shell': 'application', '/commune/angers-49007': 'fiche statique' }
  const env = { ...hosting(files), VITE_API_URL: apiUrl }
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

  describe('avec l’API', () => {
    const API = 'https://api.exemple.test/'
    afterEach(() => vi.unstubAllGlobals())

    function api(answer: number | Error) {
      const fetchMock = vi.fn<(url: string) => Promise<Response>>(() =>
        answer instanceof Error ? Promise.reject(answer) : Promise.resolve(new Response('{}', { status: answer })),
      )
      vi.stubGlobal('fetch', fetchMock)
      return fetchMock
    }

    it('répond 404 quand le code ne désigne aucune commune', async () => {
      const fetchMock = api(404)
      expect(await get('/commune/zzz-99999', API)).toEqual([404, 'introuvable'])
      expect(String(fetchMock.mock.calls[0]?.[0])).toBe('https://api.exemple.test/api/v1/communes/99999')
      await get('/commune/ajaccio-2a004', API)
      expect(String(fetchMock.mock.calls[1]?.[0])).toContain('/communes/2A004')
    })

    it('sert la fiche d’une commune connue, et dans le doute si l’API ne répond pas', async () => {
      api(200)
      expect(await get('/commune/embrun-05046', API)).toEqual([200, 'application'])
      for (const trouble of [503, 429, new Error('délai dépassé')]) {
        api(trouble)
        expect(await get('/commune/embrun-05046', API)).toEqual([200, 'application'])
      }
    })

    it('n’interroge pas l’API pour une fiche écrite ou une adresse mal formée', async () => {
      const fetchMock = api(404)
      expect(await get('/commune/angers-49007', API)).toEqual([200, 'fiche statique'])
      expect(await get('/commune/nimporte', API)).toEqual([404, 'introuvable'])
      expect(fetchMock).not.toHaveBeenCalled()
    })
  })
})
