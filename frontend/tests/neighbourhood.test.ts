import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import NeighbourhoodCard from '../src/components/cards/NeighbourhoodCard.vue'
import HomeIntro from '../src/components/HomeIntro.vue'
import ReportNav from '../src/components/ReportNav.vue'
import { districtNotice, incomeGap, incomeRange, incomeScope, populationScope, populationTrend } from '../src/lib/neighbourhood'
import { buildReportSections } from '../src/lib/report'
import { SOURCE_INFO } from '../src/lib/sources'
import { buildSteps } from '../src/lib/steps'
import { isLocked, LOCKED, teaserHook } from '../src/lib/teaser'
import type { QuartierData } from '../src/types/audit'

const INCOME = {
  annee: 2021,
  revenu_median: 27000,
  revenu_q1: 17570,
  revenu_q3: 40070,
  taux_pauvrete_pct: 17,
  reference_nationale: { revenu_median: 23160, taux_pauvrete_pct: 14.5 },
}
const POPULATION = { annee: 2022, habitants: 157555, evolution_6_ans_pct: 4.2, evolution_11_ans_pct: 5.9, arrondissement: false }
const PROFILE: QuartierData = {
  iris: { code: '490070105', nom: 'Voltaire' },
  revenus: INCOME,
  quartier_prioritaire: { dans_un_quartier: false, rayon_m: 500 },
  population: POPULATION,
}
const DISTRICT = { dans_un_quartier: false, rayon_m: 500, code: 'QN04901M', nom: 'Belle Beille', commune: 'Angers', distance_m: 15 }

/** Texte sans les espaces insécables des nombres, pour des comparaisons lisibles. */
function plain(text: string | null | undefined): string {
  return (text ?? '').replace(/[  ]/g, ' ')
}

describe('textes du profil de quartier', () => {
  it('situe le niveau de vie par rapport à la médiane nationale de la même année', () => {
    expect(plain(incomeGap(INCOME))).toBe('17 % au-dessus de la médiane nationale (23 160 €)')
    expect(plain(incomeGap({ ...INCOME, revenu_median: 17170 }))).toContain('26 % en dessous')
    expect(plain(incomeGap({ ...INCOME, revenu_median: 23160 }))).toContain('au niveau de la médiane nationale')
    expect(incomeGap({ ...INCOME, reference_nationale: null })).toBeNull()
    expect(incomeGap({ ...INCOME, revenu_median: null })).toBeNull()
    expect(plain(incomeRange(INCOME))).toBe('La moitié des habitants vit avec 17 570 € à 40 070 € par an')
    expect(incomeRange({ ...INCOME, revenu_q1: null })).toBeNull()
  })

  it('dit si les revenus sont ceux du quartier ou, à défaut, de la commune', () => {
    expect(incomeScope(PROFILE)).toBe('Quartier « Voltaire »')
    const communal = { ...INCOME, echelle: 'commune' as const }
    expect(incomeScope({ ...PROFILE, revenus: communal })).toBe('Commune entière')
    expect(incomeScope({ ...PROFILE, revenus: { ...communal, arrondissement: true } })).toBe('Arrondissement entier')

    const card = mount(NeighbourhoodCard, { props: { data: { ...PROFILE, revenus: communal } } })
    expect(card.text()).toContain('Commune entière, revenus disponibles 2021')
    expect(card.text()).toContain('ces chiffres sont ceux de la commune')
    expect(mount(NeighbourhoodCard, { props: { data: PROFILE } }).text()).not.toContain('ces chiffres sont ceux')

    const rows = JSON.stringify(buildReportSections({
      quartier: { status: 'ok', data: { ...PROFILE, revenus: communal }, missing: [], error: null, duration_ms: 1 },
    }))
    expect(rows).toContain('Niveau de vie médian (la commune, 2021)')
    expect(rows).toContain('Taux de pauvreté de la commune')
  })

  it('distingue dans le quartier prioritaire, à proximité, loin et absent', () => {
    expect(districtNotice(null)).toBeNull()
    expect(districtNotice(undefined)).toBeNull()
    expect(districtNotice(PROFILE.quartier_prioritaire)?.title).toBe('Hors quartier prioritaire')

    const inside = districtNotice({ ...DISTRICT, dans_un_quartier: true, distance_m: 0 })
    expect(inside?.title).toBe('Dans le quartier prioritaire « Belle Beille »')
    expect(inside?.detail).toContain('TVA réduite')

    const near = districtNotice(DISTRICT)
    expect(near?.title).toBe('À 15 m du quartier prioritaire « Belle Beille »')
    expect(near?.detail).toContain('bande de 300 m')

    const far = districtNotice({ ...DISTRICT, distance_m: 420 })
    expect(far?.title).toContain('420 m')
    expect(far?.detail).not.toContain('TVA')
  })

  it('résume l’évolution de la population sans inventer une tendance inconnue', () => {
    expect(plain(populationTrend(POPULATION))).toBe('+4,2 % en 6 ans, +5,9 % en 11 ans')
    expect(plain(populationTrend({ ...POPULATION, evolution_6_ans_pct: -4.8, evolution_11_ans_pct: null }))).toBe('-4,8 % en 6 ans')
    expect(populationTrend({ ...POPULATION, evolution_6_ans_pct: null, evolution_11_ans_pct: null })).toBeNull()
    expect(populationTrend(null)).toBeNull()
    expect(plain(populationScope(POPULATION))).toBe('157 555 habitants de la commune (recensement 2022)')
    expect(populationScope({ ...POPULATION, arrondissement: true })).toContain('de l’arrondissement')
  })
})

describe('carte « Profil du quartier »', () => {
  it('affiche revenus, quartier prioritaire et population', () => {
    const text = plain(mount(NeighbourhoodCard, { props: { data: PROFILE } }).text())
    expect(text).toContain('27 000 €')
    expect(text).toContain('17 %')
    expect(text).toContain('Quartier « Voltaire »')
    expect(text).toContain('Hors quartier prioritaire')
    expect(text).toContain('157 555 habitants · +4,2 % en 6 ans')
  })

  it('explique l’absence de revenus au lieu d’afficher des tirets', () => {
    const data: QuartierData = { ...PROFILE, revenus: null, quartier_prioritaire: null, population: null }
    const text = mount(NeighbourhoodCard, { props: { data } }).text()
    expect(text).toContain('L’INSEE ne diffuse les revenus ni pour ce quartier')
    expect(text).toContain('Voltaire')
    expect(text).not.toContain('quartier prioritaire')
    expect(text).not.toContain('habitants')
  })
})

describe('profil de quartier dans le reste de l’application', () => {
  it('figure dans le PDF, section « Vie de quartier »', () => {
    const result = { status: 'ok' as const, data: { ...PROFILE, quartier_prioritaire: DISTRICT }, missing: [], error: null, duration_ms: 1 }
    const section = buildReportSections({ quartier: result }).find((item) => item.title === 'Vie de quartier')
    const rows = (section?.rows ?? []).map(([label, value]) => plain(`${label} : ${value}`))
    expect(rows).toContain('Niveau de vie médian (quartier Voltaire, 2021) : 27 000 € par an, 17 % au-dessus de la médiane nationale (23 160 €)')
    expect(rows.some((row) => row.startsWith('À 15 m du quartier prioritaire « Belle Beille »'))).toBe(true)
    expect(rows).toContain('Population : 157 555 habitants de la commune (recensement 2022) ; +4,2 % en 6 ans, +5,9 % en 11 ans')
  })

  it('reste verrouillé en aperçu, avec le nom du quartier pour accroche', () => {
    const masked = { iris: PROFILE.iris, population: POPULATION, revenus: LOCKED, quartier_prioritaire: LOCKED }
    expect(isLocked(masked)).toBe(true)
    expect(teaserHook('quartier', masked)).toBe('Revenus et profil du quartier « Voltaire » analysés')
    expect(teaserHook('quartier', { iris: null })).toBe('Analyse réalisée pour cette adresse')
    expect(SOURCE_INFO.quartier.title).toBe('Profil du quartier')
  })

  it('compte dans l’étape « quartier » de la progression', () => {
    const steps = buildSteps(true, {}, ['dvf', 'quartier', 'ecoles'])
    expect(steps.find((step) => step.key === 'neighbourhood')?.expected).toBe(2)
  })
})

describe('sommaire du rapport', () => {
  const SECTIONS = [
    { id: 'section-market', label: 'Marché immobilier' },
    { id: 'section-risks', label: 'Risques et urbanisme' },
  ]

  it('mène à la section choisie et la marque comme courante', async () => {
    const target = document.createElement('h2')
    target.id = 'section-risks'
    target.scrollIntoView = vi.fn()
    document.body.append(target)

    const nav = mount(ReportNav, { props: { sections: SECTIONS } })
    const buttons = nav.findAll('button')
    expect(buttons.map((button) => button.text())).toEqual(['Marché immobilier', 'Risques et urbanisme'])
    expect(nav.find('[aria-current]').exists()).toBe(false)

    await buttons[1]?.trigger('click')

    expect(target.scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' })
    expect(nav.find('[aria-current]').text()).toBe('Risques et urbanisme')
    target.remove()
  })
})

describe('présentation de la page d’accueil', () => {
  it('donne les trois étapes, le contenu de l’audit, les sources et le prix', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/tarifs', name: 'pricing', component: { template: '<div />' } },
      ],
    })
    const intro = mount(HomeIntro, { global: { plugins: [router] } })
    const text = plain(intro.text())

    expect(intro.findAll('ol > li')).toHaveLength(3)
    expect(text).toContain('4,99 € par adresse')
    for (const heading of ['Marché immobilier', 'Risques et urbanisme', 'Énergie et environnement', 'Vie de quartier']) {
      expect(text).toContain(heading)
    }
    expect(text).toContain('INSEE')
    expect(intro.find('a').attributes('href')).toBe('/tarifs')

    await intro.find('button').trigger('click')
    expect(intro.emitted('demo')).toHaveLength(1)
  })
})
