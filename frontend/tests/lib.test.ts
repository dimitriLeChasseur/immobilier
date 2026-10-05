import { describe, expect, it } from 'vitest'

import { formatDate, formatDistance, formatPercent, formatPricePerM2, grossYield } from '../src/lib/format'
import { pdfSafe, reportFileName } from '../src/lib/pdf'
import { buildReportSections, unavailableSources } from '../src/lib/report'
import { orderedCategories } from '../src/lib/sources'
import { readTarget, writeTarget } from '../src/lib/url'
import type { SourceResult, SourceResults } from '../src/types/audit'

function ok<T>(data: T): SourceResult<T> {
  return { status: 'ok', data, missing: [], error: null, duration_ms: 1 }
}

describe('format', () => {
  it('affiche un tiret pour les valeurs absentes', () => {
    expect(formatPricePerM2(null)).toBe('—')
    expect(formatPercent(undefined)).toBe('—')
    expect(formatDate('pas une date')).toBe('—')
  })

  it('bascule en kilomètres au-delà de 1 000 m', () => {
    expect(formatDistance(350)).toBe('350 m')
    expect(formatDistance(1500)).toBe('1,5 km')
  })

  it('lit les dates compactes du Géoportail de l’urbanisme', () => {
    expect(formatDate('20260616')).toBe(formatDate('2026-06-16'))
    expect(formatDate('2026-06-16')).toContain('2026')
  })

  it('calcule le rendement brut annuel', () => {
    expect(grossYield(14, 4200)).toBeCloseTo(4, 5)
    expect(grossYield(null, 4200)).toBeNull()
    expect(grossYield(14, 0)).toBeNull()
  })
})

describe('url', () => {
  it('fait l’aller-retour d’une cible d’audit', () => {
    const search = writeTarget({ lat: 47.4712, lon: -0.5518, banId: '49007_1234_00001' }, 'Place du Ralliement')
    expect(readTarget(search)).toEqual({
      lat: 47.4712,
      lon: -0.5518,
      banId: '49007_1234_00001',
      label: 'Place du Ralliement',
    })
  })

  it('rejette les coordonnées absentes ou invalides', () => {
    expect(readTarget('')).toBeNull()
    expect(readTarget('?lat=abc&lon=2')).toBeNull()
    expect(readTarget('?lat=91&lon=2')).toBeNull()
    expect(readTarget('?lat=48&lon=181')).toBeNull()
  })
})

describe('rapport', () => {
  const sources: SourceResults = {
    dvf: ok({
      rayon_m: 300,
      nb_ventes: 42,
      prix_m2_median: 4200,
      dispersion: { min: 2600, q1: 3800, q3: 4600, max: 5400 },
      par_type: { appartement: { nb_ventes: 40, prix_m2_median: 4300 } },
      historique: [],
      dernieres_ventes: [
        { date: '2025-03-01', prix: 210000, surface_m2: 50, prix_m2: 4200, type: 'appartement', pieces: 2, distance_m: 120 },
      ],
      sections_interrogees: 3,
    }),
    loyers: ok({
      type_bien: 'appartement',
      loyer_m2_charges_comprises: 14,
      intervalle_prediction: [10, 18],
      nb_observations: 900,
      niveau_prediction: 'commune',
      millesime: 2025,
    }),
    proximite: { status: 'timeout', data: null, missing: [], error: 'Délai dépassé', duration_ms: 3000 },
    cadastre: { status: 'empty', data: null, missing: [], error: null, duration_ms: 80 },
  }

  it('ne garde que les sections ayant des données et calcule le rendement', () => {
    const sections = buildReportSections(sources)
    expect(sections.map((section) => section.title)).toEqual(['Marché immobilier'])
    const rows = Object.fromEntries(sections[0]?.rows ?? [])
    expect(rows['Rendement locatif brut (avant taxe foncière et charges)']).toBe(formatPercent(4))
    expect(sections[0]?.table?.body).toHaveLength(1)
  })

  it('signale les sources en échec, pas les sources vides', () => {
    expect(unavailableSources(sources)).toEqual(['proximite'])
  })
})

describe('pdf', () => {
  it('remplace les caractères absents des polices standard', () => {
    expect(pdfSafe('4 200 € — l’adresse ≈ 100')).toBe("4 200 € - l'adresse ~ 100")
  })

  it('dérive un nom de fichier sûr du libellé', () => {
    const location = { lat: 0, lon: 0, citycode: '49007', postcode: null, city: null, ban_id: '' }
    expect(reportFileName({ ...location, label: '5 Rue de l’Église, 49100 Angers' })).toBe(
      'audit-5-rue-de-l-eglise-49100-angers.pdf',
    )
    expect(reportFileName({ ...location, label: '../../etc' })).toBe('audit-etc.pdf')
  })
})

describe('ordre d’affichage indépendant de l’ordre des clés reçues', () => {
  it('range les catégories de proximité comme à l’écran, les inconnues à la fin', () => {
    const scrambled = { sante: 1, autre: 9, espaces_verts: 2, transports: 3, commerces: 4, education: 5 }
    expect(orderedCategories(scrambled).map(([key]) => key)).toEqual([
      'transports',
      'commerces',
      'sante',
      'education',
      'espaces_verts',
      'autre',
    ])
  })
})
