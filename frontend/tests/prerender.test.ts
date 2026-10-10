import { describe, expect, it } from 'vitest'

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
