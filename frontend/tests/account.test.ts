import { afterEach, describe, expect, it, vi } from 'vitest'

import { deleteBranding, fetchAudits, saveBranding } from '../src/api/account'
import { logoProblem, MAX_LOGO_BYTES } from '../src/lib/logo'
import { buildReportPdf, contactLine, hexToRgb, isDark, type ReportBranding } from '../src/lib/pdf'
import type { AuditLocation } from '../src/types/audit'

// Plus petit PNG valide (1 x 1 pixel), pour exercer l'insertion du logo.
const PIXEL =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
const LOCATION: AuditLocation = {
  lat: 47.4739,
  lon: -0.55083,
  label: '10 Rue du Canal 49100 Angers',
  citycode: '49007',
  postcode: '49100',
  city: 'Angers',
  ban_id: '49007_1350_00010',
}

function pdfText(branding?: ReportBranding | null): string {
  const doc = buildReportPdf({
    location: LOCATION,
    meta: null,
    sections: [{ title: 'Marché immobilier', rows: [['Prix médian', '3 684 €/m²']] }],
    charts: [],
    unavailable: [],
    branding,
  })
  return doc.output()
}

describe('marque blanche du PDF', () => {
  it('ne change rien sans marque', () => {
    const text = pdfText()
    expect(text).not.toContain('Rapport remis par')
    expect(text).toContain('Sources : ')
  })

  it('signe le rapport au nom du professionnel et garde les sources', () => {
    const text = pdfText({ company: 'Cabinet Durand', logo: null })
    expect(text).toContain('Rapport remis par Cabinet Durand')
    // Les licences des données imposent de citer les sources, marque blanche ou non.
    expect(text).toContain('Sources : ')
  })

  it('insère le logo, et se rabat sur le nom si le logo est illisible', () => {
    const withLogo = pdfText({ company: 'Cabinet Durand', logo: PIXEL })
    expect(withLogo).toContain('/Subtype /Image')
    const broken = pdfText({ company: 'Cabinet Durand', logo: 'data:image/png;base64,AAAA' })
    expect(broken).not.toContain('/Subtype /Image')
    expect(broken).toContain('Cabinet Durand')
  })
})

describe('couleur et coordonnées du professionnel', () => {
  const branding: ReportBranding = {
    company: 'Cabinet Durand',
    logo: null,
    color: '#1e40af',
    phone: '02 41 00 00 00',
    email: 'contact@durand.example',
    website: null,
    address: '',
  }

  it('lit la couleur choisie et juge sa lisibilité', () => {
    expect(hexToRgb('#1e40af')).toEqual([30, 64, 175])
    expect(hexToRgb('#1E40AF')).toEqual([30, 64, 175])
    expect(hexToRgb('bleu')).toBeNull()
    expect(hexToRgb(null)).toBeNull()
    expect(isDark([30, 64, 175])).toBe(true)
    // Sur un jaune clair, le texte de l'en-tête doit passer en foncé.
    expect(isDark([253, 224, 71])).toBe(false)
  })

  it('imprime les coordonnées renseignées, dans l’ordre, sans champ vide', () => {
    expect(contactLine(branding)).toBe('Cabinet Durand - 02 41 00 00 00 - contact@durand.example')
    expect(pdfText(branding)).toContain('Cabinet Durand - 02 41 00 00 00 - contact@durand.example')
  })

  it('applique la couleur au bandeau, et revient à la nôtre sans marque', () => {
    // Couleur de remplissage du bandeau, en composantes PDF (0 à 1).
    expect(pdfText(branding)).toContain('0.118 0.251 0.686 rg')
    expect(pdfText()).not.toContain('0.118 0.251 0.686 rg')
    expect(pdfText({ ...branding, color: 'pas une couleur' })).not.toContain('0.118 0.251 0.686 rg')
  })
})

describe('contrôle du logo avant envoi', () => {
  it('n’accepte que PNG et JPEG, sous la taille limite', () => {
    expect(logoProblem({ type: 'image/png', size: 10_000 })).toBeNull()
    expect(logoProblem({ type: 'image/jpeg', size: MAX_LOGO_BYTES })).toBeNull()
    expect(logoProblem({ type: 'image/svg+xml', size: 500 })).toBe('Le logo doit être une image PNG ou JPEG.')
    expect(logoProblem({ type: 'image/png', size: MAX_LOGO_BYTES + 1 })).toBe('Le logo doit peser moins de 200 Ko.')
  })
})

describe('appels de l’espace client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('liste les audits, enregistre la marque en PUT et la supprime en DELETE', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify([{ label: 'x', lat: 1, lon: 2 }]), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ company: 'Cabinet Durand', logo: null }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchAudits('jeton')).resolves.toHaveLength(1)
    await expect(saveBranding('jeton', { company: 'Cabinet Durand', logo: null })).resolves.toEqual({
      company: 'Cabinet Durand',
      logo: null,
    })
    await expect(deleteBranding('jeton')).resolves.toBeUndefined()

    const calls = fetchMock.mock.calls as [string, RequestInit][]
    expect(calls.map(([url, init]) => [url.replace(/^.*\/api\/v1\//, ''), init.method])).toEqual([
      ['account/audits', 'GET'],
      ['account/branding', 'PUT'],
      ['account/branding', 'DELETE'],
    ])
    expect(calls[1]?.[1].headers).toMatchObject({ Authorization: 'Bearer jeton' })
  })
})
