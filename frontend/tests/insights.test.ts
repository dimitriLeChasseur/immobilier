import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import AuditStepper from '../src/components/AuditStepper.vue'
import AirCard from '../src/components/cards/AirCard.vue'
import CondoCard from '../src/components/cards/CondoCard.vue'
import MobileNetworkCard from '../src/components/cards/MobileNetworkCard.vue'
import NoiseCard from '../src/components/cards/NoiseCard.vue'
import PropertyTaxCard from '../src/components/cards/PropertyTaxCard.vue'
import RentalMarketCard from '../src/components/cards/RentalMarketCard.vue'
import SourceCard from '../src/components/SourceCard.vue'
import VisitChecklist from '../src/components/VisitChecklist.vue'
import type { YieldLine } from '../src/lib/yield'
import YieldCard from '../src/components/cards/YieldCard.vue'
import { formatEuros, formatPercent, netYield } from '../src/lib/format'
import { inPreventionPlan, riskIndicators } from '../src/lib/insights'
import { buildReportPdf } from '../src/lib/pdf'
import { SOURCE_INFO } from '../src/lib/sources'
import { buildSteps } from '../src/lib/steps'
import { estimatePropertyTax } from '../src/lib/tax'
import type { SourceName, SourceResult } from '../src/types/audit'

const FLATS: YieldLine[] = [
  { id: 'appartement', label: 'Appartement, toutes tailles', rentPerM2: 14, pricePerM2: 4200, sales: 40, gross: 4 },
]

describe('risques', () => {
  it('reprend la recommandation calculée par le serveur', () => {
    const indicators = riskIndicators({
      radon: { classe_potentiel: '3' },
      argiles: { code: '2', exposition: 'Exposition moyenne' },
      recommandations: { radon: 'Conseil radon du serveur', argiles: 'Conseil argiles du serveur' },
    })
    const radon = indicators.find((item) => item.label === 'Radon')
    expect(radon?.tone).toBe('bad')
    expect(radon?.advice).toBe('Conseil radon du serveur')
    expect(indicators.find((item) => item.label.includes('argiles'))?.advice).toBe('Conseil argiles du serveur')
  })

  it('n’invente aucun conseil et signale les niveaux inconnus', () => {
    const indicators = riskIndicators({
      radon: { classe_potentiel: '1' },
      inondation: { concerne: false, atlas_zones_inondables: [] },
    })
    expect(indicators.every((item) => item.advice === undefined)).toBe(true)
    // Le silence de l'atlas n'est jamais présenté en vert : il ne couvre ni PPRI ni nappes.
    const flood = indicators.find((item) => item.label.startsWith('Inondation'))
    expect(flood?.tone).toBe('neutral')
    expect(flood?.value).toBe('Non répertorié dans l’atlas des zones inondables')
    expect(indicators.find((item) => item.label === 'Sismicité')?.tone).toBe('neutral')
    expect(indicators.find((item) => item.label === 'Radon')?.tone).toBe('good')
  })
})

describe('inondation : signal à l’adresse contre signal communal', () => {
  const communal = { inondation: { concerne: true, atlas_zones_inondables: ['Vallée de la Loire'] } }

  it('reste orange tant que seul l’atlas communal est connu', () => {
    const flood = riskIndicators(communal)[0]
    expect(flood?.tone).toBe('warn')
    expect(flood?.value).toContain('Commune concernée')
  })

  it('passe au rouge quand une servitude de plan de prévention couvre le point', () => {
    const zoning = { servitudes: [{ code: 'AC1' }, { code: 'PM1' }] }
    expect(inPreventionPlan(zoning)).toBe(true)
    const flood = riskIndicators(communal, inPreventionPlan(zoning))[0]
    expect(flood?.tone).toBe('bad')
    expect(flood?.value).toBe('Adresse dans le périmètre d’un plan de prévention des risques')
    expect(flood?.advice).toContain('état des risques')
  })

  it('n’affirme rien sans servitude lisible (liste absente ou masquée par le serveur)', () => {
    expect(inPreventionPlan({ servitudes: [{ code: 'AC1' }] })).toBe(false)
    expect(inPreventionPlan({ servitudes: '***LOCKED***' })).toBe(false)
    expect(inPreventionPlan(null)).toBe(false)
  })
})

describe('étapes de chargement', () => {
  const names: SourceName[] = ['dvf', 'loyers', 'georisques', 'cadastre', 'proximite']
  const answered: SourceResult<never> = { status: 'empty', data: null, missing: [], error: null, duration_ms: 1 }

  it('commence par le géocodage, les autres étapes attendant', () => {
    const steps = buildSteps(false, {}, names)
    expect(steps.map((step) => step.state)).toEqual(['active', 'pending', 'pending', 'pending', 'pending'])
    expect(steps[0]?.activeLabel).toBe('Géocodage de l’adresse…')
  })

  it('fait avancer chaque étape au rythme des sources reçues', () => {
    const steps = buildSteps(true, { dvf: answered, georisques: answered }, names)
    const byKey = Object.fromEntries(steps.map((step) => [step.key, step]))
    expect(byKey.geocoding?.state).toBe('done')
    expect(byKey.market).toMatchObject({ state: 'active', received: 1, expected: 2 })
    expect(byKey.risks).toMatchObject({ state: 'done', received: 1, expected: 1 })
    expect(byKey.planning?.state).toBe('active')
  })

  it('rattache une source inconnue à la dernière étape et ignore les étapes sans source', () => {
    const steps = buildSteps(true, {}, ['dvf', 'nouvelle_source' as SourceName])
    expect(steps.map((step) => step.key)).toEqual(['geocoding', 'market', 'neighbourhood'])
    expect(steps[2]?.expected).toBe(1)
  })

  it('affiche les étapes et rassure quand l’attente se prolonge', async () => {
    vi.useFakeTimers()
    const stepper = mount(AuditStepper, { props: { located: true, sources: {}, sourceNames: names } })
    expect(stepper.text()).toContain('Adresse localisée')
    expect(stepper.text()).toContain('Calcul du marché immobilier…')
    expect(stepper.text()).not.toContain('répondent lentement')
    // 1 étape acquise (géocodage) sur 6 éléments attendus (géocodage + 5 sources).
    expect(stepper.find('progress').attributes('value')).toBe('17')

    await vi.advanceTimersByTimeAsync(5000)
    expect(stepper.text()).toContain('répondent lentement')
    stepper.unmount()
    vi.useRealTimers()
  })
})

describe('réseau mobile et bruit', () => {
  it('liste les opérateurs, leurs générations et la 5G', () => {
    const card = mount(MobileNetworkCard, {
      props: {
        data: {
          rayon_m: 1000,
          nb_sites: 17,
          operateurs: [
            { nom: 'Orange', generations: ['4G', '5G'], nb_sites: 8, site_le_plus_proche_m: 104 },
            { nom: 'Free Mobile', generations: ['4G'], nb_sites: 5, site_le_plus_proche_m: 190 },
          ],
          operateurs_5g: ['Orange'],
          liste_tronquee: false,
        },
      },
    })
    expect(card.text()).toContain('17 sites')
    expect(card.text()).toContain('5G déployée par Orange')
    expect(card.text()).toContain('le plus proche à 190 m')
  })

  it('affiche la classe de bruit la plus forte et le message du serveur', () => {
    const loud = mount(NoiseCard, {
      props: {
        data: {
          indice: 'Lden',
          niveau_max_db: 70,
          sources: [{ infrastructure: 'fer', db_min: 70, db_max: 75 }],
          message: 'Exposition très forte.',
        },
      },
    })
    expect(loud.text()).toContain('70 à 75 dB')
    expect(loud.text()).toContain('Voie ferrée')
    expect(loud.text()).toContain('Exposition très forte.')

    const quiet = mount(NoiseCard, {
      props: { data: { indice: 'Lden', niveau_max_db: null, sources: [], message: 'Calme.' } },
    })
    expect(quiet.text()).toContain('Moins de 55 dB')

    // Seul le ferroviaire est cartographié : le calme affiché ne doit pas couvrir la route.
    const railOnly = mount(NoiseCard, {
      props: {
        data: { indice: 'Lden', niveau_max_db: null, sources: [], infrastructures_couvertes: ['fer'], message: 'x' },
      },
    })
    expect(railOnly.text()).toContain('Moins de 55 dB (voie ferrée seulement)')
    expect(railOnly.find('.text-emerald-700, .text-emerald-600').exists()).toBe(false)
  })
})

describe('rendement net', () => {
  const base = { rentPerM2: 14, pricePerM2: 4200, surfaceM2: 50 }

  it('égale le brut sans charges, puis baisse avec la taxe foncière et les charges', () => {
    expect(netYield({ ...base, propertyTax: 0, condoCharges: 0 })).toBeCloseTo(4, 5)
    // 8 400 € de loyers - 900 - 1 000 = 6 500 € sur 210 000 €
    expect(netYield({ ...base, propertyTax: 900, condoCharges: 1000 })).toBeCloseTo(3.095, 2)
  })

  it('refuse une surface nulle', () => {
    expect(netYield({ ...base, surfaceM2: 0, propertyTax: 0, condoCharges: 0 })).toBeNull()
  })

  it('reprend les charges du bloc copropriété et recalcule quand la taxe foncière est saisie', async () => {
    const card = mount(YieldCard, {
      props: { loading: false, lines: FLATS, surface: 50, condoChargesEstimate: 1000, propertyTaxRate: 56.65 },
    })
    const inputs = card.findAll('input')
    expect((inputs[2]?.element as HTMLInputElement).value).toBe('1000')
    expect(card.text()).toContain('hors taxe foncière')
    expect(card.text()).toContain(formatPercent((7400 * 100) / 210000))

    await inputs[1]?.setValue(900)
    expect(card.text()).not.toContain('hors taxe foncière')
    expect(card.text()).toContain(formatPercent((6500 * 100) / 210000))
  })

  it('suit le bloc copropriété tant que le champ du simulateur n’est pas modifié', async () => {
    const card = mount(YieldCard, {
      props: { loading: false, lines: FLATS, surface: 50, condoChargesEstimate: 1000, propertyTaxRate: null },
    })
    const chargesInput = card.findAll('input')[2]
    await card.setProps({ condoChargesEstimate: 1450 })
    expect((chargesInput?.element as HTMLInputElement).value).toBe('1450')

    await chargesInput?.setValue(1800)
    await card.setProps({ condoChargesEstimate: 900 })
    expect((chargesInput?.element as HTMLInputElement).value).toBe('1800')
  })
})

describe('charges de copropriété', () => {
  const data = {
    charges_m2_an: 20.06,
    niveau: 'region',
    territoire: 'Pays de la Loire',
    millesime: 2018,
    origine: 'Annonces immobilières',
  } as const

  it('préremplit le champ avec la moyenne et l’annonce comme une estimation', () => {
    const card = mount(CondoCard, { props: { data, surfaceM2: 50 } })
    expect((card.find('input').element as HTMLInputElement).value).toBe('1003')
    expect(card.text()).toContain('Valeur estimée (Moyenne régionale 2018 : 20,1 €/m²)')
    expect(card.text()).toContain('Modifiez avec le montant exact de l’annonce.')
    expect(card.emitted('charges')?.at(-1)).toEqual([1003])
  })

  it('suit la surface tant que rien n’est saisi, puis respecte la saisie', async () => {
    const card = mount(CondoCard, { props: { data, surfaceM2: 50 } })
    await card.setProps({ surfaceM2: 80 })
    expect((card.find('input').element as HTMLInputElement).value).toBe('1605')

    await card.find('input').setValue(2400)
    await card.setProps({ surfaceM2: 100 })
    expect((card.find('input').element as HTMLInputElement).value).toBe('2400')
    expect(card.emitted('charges')?.at(-1)).toEqual([2400])
  })

  it('permet de revenir à l’estimation et transmet un champ vidé', async () => {
    const card = mount(CondoCard, { props: { data, surfaceM2: 50 } })
    await card.find('input').setValue('')
    expect(card.emitted('charges')?.at(-1)).toEqual([null])

    await card.find('button').trigger('click')
    expect((card.find('input').element as HTMLInputElement).value).toBe('1003')
    expect(card.emitted('charges')?.at(-1)).toEqual([1003])
    expect(card.find('button').exists()).toBe(false)
  })

  it('parle de moyenne de la ville quand elle existe', () => {
    const card = mount(CondoCard, {
      props: { data: { ...data, niveau: 'ville', territoire: 'Nantes', charges_m2_an: 20.72 }, surfaceM2: 50 },
    })
    expect(card.text()).toContain('Moyenne de la ville 2018 : 20,7 €/m²')
  })
})

describe('qualité de l’air', () => {
  const data = {
    indice: 3,
    qualificatif: 'Dégradé',
    date: '2026-10-05',
    zone: { code: '49007', nom: 'Angers', type: 'commune' },
    sous_indices: { pm2_5: 1, pm10: 1, no2: 1, o3: 3, so2: null },
    polluants_dominants: ['ozone'],
    demain: { indice: 2, qualificatif: 'Moyen' },
    producteur: 'Air Pays de la Loire',
    origine: 'Atmo France (indice ATMO, licence ODbL)',
  }

  it('affiche l’indice ATMO, ce qui le détermine, la prévision et la source', () => {
    const text = mount(AirCard, { props: { data } }).text()
    expect(text).toContain('Dégradé')
    expect(text).toContain('Niveau 3 sur 6')
    expect(text).toContain('Déterminé par : ozone.')
    expect(text).toContain('Prévision pour demain : moyen (2 / 6)')
    expect(text).toContain('calculé pour la commune')
    expect(text).toContain('Air Pays de la Loire, Atmo France')
    expect(text).not.toContain('Dioxyde de soufre')
  })

  it('précise quand l’indice est celui de l’intercommunalité', () => {
    const zone = { code: '200071553', nom: 'CC Loire Layon Aubance', type: 'epci' }
    const text = mount(AirCard, { props: { data: { ...data, zone, demain: null } } }).text()
    expect(text).toContain('l’intercommunalité (CC Loire Layon Aubance)')
    expect(text).not.toContain('Prévision pour demain')
  })
})

describe('transparence sur les données manquantes', () => {
  it('présente une source sans donnée dans un encart gris, pas comme une erreur', () => {
    const card = mount(SourceCard, {
      props: {
        ...SOURCE_INFO.bruit,
        result: { status: 'empty', data: null, missing: [], error: null, duration_ms: 3 },
      },
    })
    const notice = card.find('p')
    expect(notice.text()).toBe('Cartes de bruit non intégrées à notre base pour ce secteur : consultez celles de la préfecture.')
    expect(notice.classes()).toContain('bg-slate-100')
    expect(card.text()).not.toContain('Indisponible')
  })

  it('renvoie vers le simulateur officiel quand l’encadrement est partiel', () => {
    const card = mount(RentalMarketCard, {
      props: {
        data: {
          occupation: null,
          encadrement_loyers: { statut: 'partiel', territoire: 'Grenoble-Alpes Métropole', verifie_le: '2026-08-01' },
          permis_de_louer: { statut: 'inconnu' },
        },
      },
    })
    const link = card.find('a')
    expect(link.attributes('href')).toBe('https://www.service-public.fr/simulateur/calcul/zones-tendues')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toContain('noopener')
    expect(link.text()).toContain('Application partielle selon les communes.')
    expect(link.text()).toContain('Vérifier sur le simulateur officiel du Service Public')
  })

  it('n’affiche pas ce lien quand la règle est claire', () => {
    const card = mount(RentalMarketCard, {
      props: {
        data: {
          occupation: null,
          encadrement_loyers: { statut: 'oui', territoire: 'Paris', verifie_le: '2026-08-01' },
          permis_de_louer: { statut: 'inconnu' },
        },
      },
    })
    expect(card.find('a').exists()).toBe(false)
  })
})

describe('checklist de contre-visite', () => {
  it('affiche les trois points à vérifier sous forme de cases à cocher', () => {
    const checklist = mount(VisitChecklist, { props: { modelValue: [] } })
    expect(checklist.find('h2').text()).toBe('Checklist de Contre-Visite')
    expect(checklist.findAll('input[type="checkbox"]')).toHaveLength(3)
    const text = checklist.text()
    expect(text).toContain('Demander au vendeur la facture de la fibre optique')
    expect(text).toContain('Vérifier en mairie si l’adresse est soumise au permis de louer.')
    expect(text).toContain('Demander le DPE complet')
    expect(text).toContain('3 point(s) restant à vérifier.')
  })

  it('remonte les cases cochées et le décompte', async () => {
    const checklist = mount(VisitChecklist, {
      props: {
        modelValue: [] as string[],
        'onUpdate:modelValue': (value: string[]) => checklist.setProps({ modelValue: value }),
      },
    })
    await checklist.findAll('input')[1]?.setValue(true)
    expect(checklist.props('modelValue')).toEqual(['permis_louer'])
    expect(checklist.text()).toContain('2 point(s) restant à vérifier.')
  })

  it('figure dans le PDF, avec ou sans cases cochées', () => {
    const location = { lat: 47.47, lon: -0.55, label: 'Angers', citycode: '49007', postcode: null, city: null, ban_id: '' }
    const base = { location, meta: null, sections: [], charts: [], unavailable: [] }
    const content = (checkedItems: string[]): string => buildReportPdf({ ...base, checkedItems }).output()

    const blank = content([])
    expect(blank).toContain('Checklist de Contre-Visite')
    expect(blank).toContain('Demander le DPE complet')
    expect(blank).toContain('permis de louer')
    // Une case cochée ajoute des tracés (la coche) au document.
    expect(content(['fibre', 'dpe']).length).toBeGreaterThan(blank.length)
  })
})

describe('simulateur de taxe foncière', () => {
  const data = {
    annee: 2025,
    libelle_commune: 'ANGERS',
    taux_tfb_commune: 54.24,
    taux_tfb_epci: 2.18,
    taux_tfb_total: 56.65,
    taux_teom: 8.71,
  }

  it('applique le taux à la moitié de la valeur locative cadastrale', () => {
    const estimate = estimatePropertyTax(3200, 56.65, 8.71)
    expect(estimate?.taxableBase).toBe(1600)
    expect(estimate?.propertyTax).toBeCloseTo(906.4, 5)
    expect(estimate?.wasteTax).toBeCloseTo(139.36, 5)
    expect(estimate?.total).toBeCloseTo(1045.76, 5)
  })

  it('ignore les saisies vides, négatives ou manifestement erronées', () => {
    expect(estimatePropertyTax(null, 56.65, 8.71)).toBeNull()
    expect(estimatePropertyTax(0, 56.65, 8.71)).toBeNull()
    expect(estimatePropertyTax(-10, 56.65, 8.71)).toBeNull()
    expect(estimatePropertyTax(900_000, 56.65, 8.71)).toBeNull()
    expect(estimatePropertyTax(Number.NaN, 56.65, 8.71)).toBeNull()
  })

  it('gère une commune sans taxe d’ordures ménagères', () => {
    const estimate = estimatePropertyTax(2000, 30, null)
    expect(estimate).toEqual({ taxableBase: 1000, propertyTax: 300, wasteTax: null, total: 300 })
  })

  it('affiche les taux, calcule à la saisie et transmet le montant', async () => {
    const card = mount(PropertyTaxCard, { props: { data } })
    expect(card.text()).toContain('56,65 %')
    expect(card.text()).toContain('8,71 %')
    expect(card.find('output').exists()).toBe(false)

    await card.find('input').setValue(3200)
    expect(card.find('output').text()).toContain(formatEuros(906.4))
    expect(card.find('output').text()).toContain(formatEuros(1045.76))
    expect(card.emitted('estimate')?.at(-1)).toEqual([906])

    await card.find('input').setValue('')
    expect(card.find('output').exists()).toBe(false)
    expect(card.emitted('estimate')?.at(-1)).toEqual([null])
  })

  it('signale une valeur qui ressemble à un prix de vente', async () => {
    const card = mount(PropertyTaxCard, { props: { data } })
    await card.find('input').setValue(650000)
    expect(card.find('[role="alert"]').text()).toContain('pas le prix du bien')
  })

  it('alimente le calcul de rendement tant que l’utilisateur n’a pas saisi son propre montant', async () => {
    const card = mount(YieldCard, {
      props: { loading: false, lines: FLATS, surface: 50, condoChargesEstimate: null, propertyTaxRate: 56.65 },
    })
    await card.setProps({ propertyTaxEstimate: 906 })
    const taxInput = card.findAll('input')[1]
    expect((taxInput?.element as HTMLInputElement).value).toBe('906')
    expect(card.text()).not.toContain('hors taxe foncière')

    await taxInput?.setValue(1200)
    await card.setProps({ propertyTaxEstimate: 950 })
    expect((taxInput?.element as HTMLInputElement).value).toBe('1200')
  })
})
