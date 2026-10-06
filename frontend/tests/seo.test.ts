import { afterEach, describe, expect, it } from 'vitest'

import { codeFromSlug, communePage, type CommuneProfile } from '../src/lib/commune'
import { setPageMeta } from '../src/lib/seo'

const ANGERS: CommuneProfile = {
  code: '49007',
  nom: 'Angers',
  slug: 'angers-49007',
  departement_code: '49',
  departement_nom: 'Maine-et-Loire',
  population: 159022,
  codes_postaux: ['49000', '49100'],
  centre: [-0.5629, 47.4819],
  taxe_fonciere: { annee: 2025, taux_tfb_total: { valeur: 56.65, departement: 46.57, national: 40.33 }, taux_teom: 8.71 },
  delinquance: { annee: 2025, cambriolages: { valeur: 1.69, departement: 1.97, national: 3.27 }, annee_precedente: 2.29 },
  ecoles: { ecole: { nb: 52, ips_moyen: 105.7, moyenne_nationale: 104.8 } },
  part_fibre_pct: 97.3,
  loyers: { appartement: 14.6, t1_t2: 16.6 },
  logement: { annee: 2022, logements: 92383, part_locataires_pct: 66.3, part_proprietaires_pct: 32.4, part_vacants_pct: 6 },
}

describe('fiche communale', () => {
  it('compose titre, description et chiffres comparés', () => {
    const page = communePage(ANGERS)
    expect(page.title).toBe('Immobilier à Angers (49) : loyers, taxe foncière, sécurité, écoles | Audit Immobilier')
    expect(page.description).toContain('Angers')
    expect(page.description.length).toBeLessThan(260)
    expect(page.sections.map((section) => section.heading)).toEqual([
      'Loyers d’annonce',
      'Fiscalité locale',
      'Sécurité',
      'Établissements scolaires',
      'Logement et connexion',
    ])
  })

  it('donne chaque chiffre avec son repère', () => {
    // Premier fait de chaque rubrique, espaces insécables ramenés à des espaces simples.
    const first = (heading: string) => {
      const fact = communePage(ANGERS).sections.find((section) => section.heading === heading)?.facts[0]
      return [fact?.label, fact?.value, fact?.note].map((text) => text?.replace(/\s/g, ' '))
    }
    expect(first('Loyers d’annonce')).toEqual(['Appartement', '14,6 €/m² par mois, charges comprises', undefined])
    expect(first('Fiscalité locale').slice(1)).toEqual([
      '56,65 %',
      'Commune médiane du département : 46,57 % · France : 40,33 %',
    ])
    expect(first('Sécurité').slice(1)).toEqual([
      '1,7 pour 1 000 habitants, en baisse sur un an',
      'Maine-et-Loire : 2,0 · France : 3,3',
    ])
    expect(first('Établissements scolaires')[0]).toBe('Écoles (52)')
  })

  it('omet les rubriques sans donnée plutôt que d’afficher des vides', () => {
    const page = communePage({
      ...ANGERS,
      taxe_fonciere: null,
      delinquance: null,
      ecoles: {},
      logement: null,
      loyers: {},
      part_fibre_pct: null,
      population: null,
    })
    expect(page.sections).toEqual([])
    expect(page.description).toContain('données publiques')
    expect(page.intro).not.toContain('habitants')
  })

  it('ne lit le code INSEE que dans un segment bien formé', () => {
    expect(codeFromSlug('angers-49007')).toBe('49007')
    expect(codeFromSlug('ajaccio-2a004')).toBe('2A004')
    expect(codeFromSlug('saint-etienne-42218')).toBe('42218')
    expect(codeFromSlug('angers')).toBeNull()
    expect(codeFromSlug('angers-4900')).toBeNull()
  })
})

describe('balises de page', () => {
  afterEach(() => {
    document.head.innerHTML = ''
  })

  it('met à jour titre, description, canonique et consigne d’indexation sans doublon', () => {
    setPageMeta({ title: 'Tarifs', description: 'Grille', path: '/tarifs' })
    setPageMeta({ title: 'Audit : 8 Rue du Canal', description: 'Rapport', path: '/', noindex: true })

    expect(document.title).toBe('Audit : 8 Rue du Canal')
    expect(document.head.querySelectorAll('meta[name="description"]')).toHaveLength(1)
    expect(document.head.querySelector('meta[name="description"]')?.getAttribute('content')).toBe('Rapport')
    expect(document.head.querySelector('meta[name="robots"]')?.getAttribute('content')).toBe('noindex, follow')
    expect(document.head.querySelectorAll('link[rel="canonical"]')).toHaveLength(1)
    expect(document.head.querySelector('link[rel="canonical"]')?.getAttribute('href')).toMatch(/\/$/)
    expect(document.head.querySelector('meta[property="og:title"]')?.getAttribute('content')).toBe(
      'Audit : 8 Rue du Canal',
    )
  })
})
