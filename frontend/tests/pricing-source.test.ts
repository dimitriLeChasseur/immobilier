import { describe, expect, it, vi } from 'vitest'

import { renderPage } from '../src/prerender'

// Un prix fictif : chaque texte qui le reprend doit le lire dans `lib/pricing.ts`, sinon un
// changement de prix laisserait l'ancien montant affiché quelque part.
vi.mock('../src/lib/pricing', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../src/lib/pricing')>()),
  UNIT_PRICE: '9,99 €',
}))

describe('prix à l’unité de la page tarifs', () => {
  it('vient de la grille tarifaire, dans le titre comme dans la description', async () => {
    const page = await renderPage('/tarifs')
    expect(page.description).toContain('9,99 €')
    expect(page.description).not.toContain('2,99')
    expect(page.body).toMatch(/<h1[^>]*>\s*9,99 €/)
  })
})
