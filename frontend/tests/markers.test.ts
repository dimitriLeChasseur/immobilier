import { describe, expect, it } from 'vitest'

import { communeSlug } from '../src/lib/commune'
import { mapMarkers } from '../src/lib/markers'
import type { SourceResult, SourceResults } from '../src/types/audit'

function ok<T>(data: T): SourceResult<T> {
  return { status: 'ok', data, missing: [], error: null, duration_ms: 1 }
}

describe('points placés sur la carte', () => {
  it('réunit ventes, écoles et permis géolocalisés', () => {
    const sources = {
      dvf: ok({
        points: [
          [-0.551, 47.474, 3750, 1, 2025],
          [-0.552, 47.4745, 3700, 4, 2024],
        ],
      }),
      ecoles: ok({
        etablissements: [
          { nom: 'ECOLE JOSEPH CUSSONNEAU', ips: 127.7, lat: 47.475, lon: -0.552 },
          { nom: 'Sans position', ips: 100 },
        ],
      }),
      permis_construire: ok({
        permis: [{ adresse: '31 RUE DU CORNET', date_autorisation: '2025-05-20', lat: 47.4745, lon: -0.5505 }],
      }),
    } as unknown as SourceResults
    const markers = mapMarkers(sources)
    expect(markers.map((marker) => marker.kind)).toEqual(['vente', 'vente', 'ecole', 'permis'])
    expect(markers[0]?.label.replace(/\s/g, ' ')).toBe('Vente de 2025 : 3 750 €/m²')
    // Les ventes d'un même immeuble forment un seul point, lisible au survol.
    expect(markers[1]?.label.replace(/\s/g, ' ')).toBe('4 ventes, médiane 3 700 €/m² (dernière en 2024)')
    expect(markers[1]?.weight).toBe(4)
    expect(markers[2]).toMatchObject({ lat: 47.475, lon: -0.552, label: 'ECOLE JOSEPH CUSSONNEAU (IPS 128)' })
    expect(markers[3]?.label).toContain('31 RUE DU CORNET')
  })

  it('ne place rien quand le serveur a masqué les positions (aperçu gratuit)', () => {
    const locked = {
      dvf: ok({ points: '***LOCKED***' }),
      ecoles: ok({ etablissements: '***LOCKED***' }),
      permis_construire: ok({ permis: '***LOCKED***' }),
    } as unknown as SourceResults
    expect(mapMarkers(locked)).toEqual([])
    expect(mapMarkers({})).toEqual([])
  })
})

describe('adresse de la fiche d’une commune', () => {
  it('suit la même règle que le serveur', () => {
    expect(communeSlug('Angers', '49007')).toBe('angers-49007')
    expect(communeSlug('Saint-Étienne', '42218')).toBe('saint-etienne-42218')
    expect(communeSlug("L'Haÿ-les-Roses", '94038')).toBe('l-hay-les-roses-94038')
    expect(communeSlug('Ajaccio', '2A004')).toBe('ajaccio-2a004')
  })
})
