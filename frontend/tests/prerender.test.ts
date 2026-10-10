import { describe, expect, it, vi } from 'vitest'

import { LEGAL_INCOMPLETE } from '../src/lib/legal'
import { UNIT_PRICE } from '../src/lib/pricing'
import { renderPage } from '../src/prerender'

describe('rendu statique des pages publiques', () => {
  it('écrit le contenu de l’accueil', async () => {
    const page = await renderPage('/')
    expect(page.title).toContain('Audit Immobilier')
    expect(page.body).toContain('<h1')
    expect(page.body).toContain('Comment ça marche')
    expect(page.body).toContain('Ce que contient l’audit complet')
    expect(page.body).toContain(UNIT_PRICE)
  })

  it('écrit la grille tarifaire avec ses propres balises', async () => {
    const page = await renderPage('/tarifs')
    expect(page.title).toContain('Tarifs')
    expect(page.description).toContain('4,99')
    expect(page.body).toContain('Contre-Visite')
    expect(page.body).toContain('Pack Investisseur')
    expect(page.body).not.toContain('Comment ça marche')
  })

  it('refuse une page inconnue', async () => {
    await expect(renderPage('/page-inexistante')).rejects.toThrow('inconnue')
  })
})

describe('rendu statique des pages secondaires', () => {
  it('écrit la liste des communes chargée avant l’affichage', async () => {
    const links = [{ nom: 'Angers', slug: 'angers-49007', departement_code: '49' }]
    vi.stubGlobal('fetch', () => Promise.resolve(new Response(JSON.stringify(links))))
    const page = await renderPage('/communes')
    vi.unstubAllGlobals()
    expect(page.body).toContain('Département 49')
    expect(page.body).toContain('href="/commune/angers-49007"')
    expect(page.noindex).toBe(false)
  })

  it('écrit les pages légales, hors index tant que l’éditeur est incomplet', async () => {
    const page = await renderPage('/cgv')
    expect(page.body).toContain('<h1')
    expect(page.body).toContain('Dernière mise à jour')
    expect(page.noindex).toBe(LEGAL_INCOMPLETE)
  })
})
