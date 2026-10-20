import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ClimateCard from '../src/components/cards/ClimateCard.vue'

import { climateRows, energyRows, episodesNotice } from '../src/lib/air'
import { buildReportSections } from '../src/lib/report'
import type { ClimatAirEnergieData, EpisodesPollution } from '../src/types/audit'

/** Texte sans les espaces insécables des nombres, pour des comparaisons lisibles. */
function plain(text: string | null | undefined): string {
  return (text ?? '').replace(/[  ]/g, ' ')
}

const EPISODES: EpisodesPollution = {
  zone: { code: '2003', nom: 'Bassin Lyon Nord-Isère' },
  debut: '2025-10-20',
  fin: '2026-10-19',
  suivi_quotidien: false,
  nb_jours: 25,
  nb_jours_alerte: 6,
  par_polluant: [
    { polluant: 'o3', libelle: 'ozone', nb_jours: 15, nb_jours_alerte: 5 },
    { polluant: 'pm10', libelle: 'particules PM10', nb_jours: 1, nb_jours_alerte: 0 },
  ],
}

const ENERGY = { electricite: 47.6, gaz: 34.5, produits_petroliers: 5.5, bois: 4.3, reseau_chaleur: 8.1, autres: 0 }
const CLIMATE: ClimatAirEnergieData = {
  territoire: { code: '200046977', nom: 'Métropole de Lyon' },
  millesime: 2022,
  version_inventaire: 'M2024',
  producteur: 'Atmo Auvergne-Rhône-Alpes',
  ges: { t_par_habitant: 3.45, evolution_depuis_2018_pct: -18.4, repere_t_par_habitant: 5.73 },
  nox: { t_par_km2: 13.137, secteur_dominant: 'Transport routier', repere_t_par_km2: 1.212 },
  pm2_5: { t_par_km2: 1.7, secteur_dominant: null, repere_t_par_km2: 0.328 },
  energie_residentiel_tertiaire: ENERGY,
  repere: {
    territoire: 'France métropolitaine',
    millesime: 2022,
    energie_residentiel_tertiaire: { electricite: 45.9, gaz: 26.9, produits_petroliers: 9.6, bois: 12.5, reseau_chaleur: 4.2, autres: 0.9 },
  },
  origine: 'Atmo France (inventaires territoriaux, licence ODbL)',
}

describe('épisodes de pollution', () => {
  it('compte les jours par polluant et rappelle que seuls les épisodes sont publiés', () => {
    const notice = episodesNotice(EPISODES)
    expect(notice.title).toBe('25 jours d’épisode de pollution en 12 mois, dont 6 en alerte')
    expect(notice.lines).toEqual(['Ozone : 15 jours, dont 5 en alerte', 'Particules PM10 : 1 jour'])
    expect(plain(notice.detail)).toBe(
      'Zone Bassin Lyon Nord-Isère, du 20 oct. 2025 au 19 oct. 2026. Jours d’épisode publiés par ' +
        'l’association régionale de surveillance de l’air ; son historique peut être incomplet.',
    )
  })

  it('ne lit jamais « aucun épisode » quand la zone ne publie que ses épisodes', () => {
    const silent = episodesNotice({ ...EPISODES, nb_jours: 0, nb_jours_alerte: 0, par_polluant: [], zone: { code: '49', nom: null } })
    expect(silent.title).toBe('Aucun épisode de pollution publié en 12 mois')
    expect(silent.detail).toContain('leur absence ne prouve pas que l’air soit resté sous les seuils')

    const tracked = episodesNotice({ ...EPISODES, nb_jours: 0, nb_jours_alerte: 0, par_polluant: [], suivi_quotidien: true })
    expect(tracked.title).toBe('Aucun épisode de pollution en 12 mois')
    expect(tracked.detail).toContain('Suivi publié chaque jour')
  })
})

describe('inventaire du territoire', () => {
  it('rapporte chaque émission au repère métropolitain de la même année', () => {
    expect(climateRows(CLIMATE).map(([label, value]) => [label, plain(value)])).toEqual([
      ['Gaz à effet de serre', '3,5 t éq. CO₂ par habitant, en baisse de 18,4 % depuis 2018 (France métropolitaine : 5,7 t)'],
      ['Oxydes d’azote (NOx)', '13,1 t par km², premier secteur émetteur : transport routier (France métropolitaine : 1,2 t)'],
      ['Particules fines (PM2.5)', '1,7 t par km² (France métropolitaine : 0,3 t)'],
    ])
  })

  it('met chaque énergie des logements et bureaux face à la métropole, de la plus utilisée à la moins utilisée', () => {
    expect(energyRows(CLIMATE).map((row) => ({ ...row, local: plain(row.local), reference: plain(row.reference) }))).toEqual([
      { label: 'Électricité', local: '47,6 %', reference: '45,9 %' },
      { label: 'Gaz naturel', local: '34,5 %', reference: '26,9 %' },
      { label: 'Réseau de chaleur', local: '8,1 %', reference: '4,2 %' },
      { label: 'Fioul et autres produits pétroliers', local: '5,5 %', reference: '9,6 %' },
      { label: 'Bois', local: '4,3 %', reference: '12,5 %' },
    ])
    expect(energyRows({ ...CLIMATE, energie_residentiel_tertiaire: null })).toEqual([])
  })

  it('figure dans la section environnement du PDF avec son millésime', () => {
    const environment = buildReportSections({
      climat_air_energie: { status: 'ok', data: CLIMATE, missing: [], error: null, duration_ms: 1 },
      qualite_air: { status: 'ok', data: { episodes: EPISODES }, missing: [], error: null, duration_ms: 1 },
    }).find((section) => section.title === 'Énergie et environnement')
    const rows = (environment?.rows ?? []).map(([label, value]) => [label, plain(value)])
    expect(rows).toContainEqual([
      'Épisodes de pollution (12 mois)',
      '25 jours d’épisode de pollution en 12 mois, dont 6 en alerte. Ozone : 15 jours, dont 5 en alerte ; Particules PM10 : 1 jour. ' +
        'Zone Bassin Lyon Nord-Isère, du 20 oct. 2025 au 19 oct. 2026. Jours d’épisode publiés par ' +
        'l’association régionale de surveillance de l’air ; son historique peut être incomplet.',
    ])
    expect(rows).toContainEqual([
      'Inventaire 2022 de Métropole de Lyon',
      'Atmo Auvergne-Rhône-Alpes, version M2024',
    ])
    expect(rows).toContainEqual([
      'Énergie des logements et bureaux',
      'Électricité 47,6 %, Gaz naturel 34,5 %, Réseau de chaleur 8,1 %, Fioul et autres produits pétroliers 5,5 %, Bois 4,3 %',
    ])
  })
})

describe('carte de l’inventaire du territoire', () => {
  it('dit que les chiffres sont ceux de l’intercommunalité et compare ses énergies à la métropole', () => {
    const card = mount(ClimateCard, { props: { data: CLIMATE } })
    const text = plain(card.text())
    expect(text).toContain('l’intercommunalité Métropole de Lyon, et non l’adresse')
    expect(card.findAll('tbody tr')).toHaveLength(5)
    expect(card.find('thead').text()).toContain('France métropolitaine')
    expect(text).toContain('Inventaire 2022 (version M2024), produit par Atmo Auvergne-Rhône-Alpes')
  })

  it('n’affiche pas de tableau des énergies quand l’inventaire n’a que des totaux', () => {
    const card = mount(ClimateCard, { props: { data: { ...CLIMATE, energie_residentiel_tertiaire: null, repere: null } } })
    expect(card.find('table').exists()).toBe(false)
    expect(card.text()).not.toContain('Repère')
  })
})
