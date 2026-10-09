import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import BuildingCard from '../src/components/cards/BuildingCard.vue'
import ParcelCard from '../src/components/cards/ParcelCard.vue'
import RentCard from '../src/components/cards/RentCard.vue'
import RisksCard from '../src/components/cards/RisksCard.vue'
import ZoningCard from '../src/components/cards/ZoningCard.vue'
import { buildReportSections } from '../src/lib/report'
import type { BatimentData, SourceResult } from '../src/types/audit'

const BUILDING: BatimentData = {
  adresse: '17 Rue Saint-Aubin 49100 Angers',
  annee_construction: 1850,
  usage: 'Résidentiel collectif',
  nb_niveaux: 5,
  hauteur_m: 15,
  nb_logements: 8,
  materiaux: { murs: null, toit: 'Ardoises' },
  chauffage: { energie: 'Électricité', installation: 'Individuel' },
  dpe: { classe: 'C', repartition: { C: 1, D: 4, E: 1 } },
  monument_historique: { dans_perimetre: true, nom: 'Immeuble', distance_m: 28 },
  copropriete: {
    nom: '17 RUE SAINT AUBIN',
    immatriculation: 'AC7157225',
    nb_lots: 18,
    nb_logements: 8,
    nb_lots_stationnement: 0,
    nb_lots_tertiaires: 1,
    annee_construction: 1850,
  },
  origine: 'Base de données nationale des bâtiments (CSTB)',
}

function ok<T>(data: T): SourceResult<T> {
  return { status: 'ok', data, missing: [], error: null, duration_ms: 1 }
}

describe('bâtiment et copropriété', () => {
  it('décrit le bâtiment sans afficher les caractéristiques inconnues', () => {
    const card = mount(BuildingCard, { props: { data: BUILDING } })
    const text = card.text()
    expect(text).toContain('1850')
    expect(text).toContain('5 (environ 15 m)')
    expect(text).toContain('Ardoises')
    expect(text).not.toContain('Murs')
    expect(text).toContain('Électricité, individuel')
    expect(text).toContain('1 C · 4 D · 1 E')
    expect(text).toContain('Copropriété de 18 lots, dont 8 logements')
    expect(text).toContain('AC7157225')
    expect(text).toContain('Abords d’un monument historique (Immeuble, à 28 m)')
  })

  it('distingue l’absence de copropriété du registre sans réponse', () => {
    const none = mount(BuildingCard, { props: { data: { ...BUILDING, copropriete: null } } })
    expect(none.text()).toContain('Aucune copropriété immatriculée')
    const withoutAnswer: BatimentData = { ...BUILDING }
    delete withoutAnswer.copropriete
    const unknown = mount(BuildingCard, { props: { data: withoutAnswer } })
    expect(unknown.text()).not.toContain('copropriété immatriculée')
    expect(unknown.text()).not.toContain('Copropriété de')
  })

  it('précise quand la parcelle vient de l’adresse et non du point', () => {
    const parcel = { identifiant: '49007000DE0115', section: 'DE', numero: '0115', contenance_m2: 106, commune: 'Angers' }
    expect(mount(ParcelCard, { props: { data: { ...parcel, origine: 'adresse' } } }).text()).toContain(
      'Parcelle rattachée à cette adresse',
    )
    expect(mount(ParcelCard, { props: { data: { ...parcel, origine: 'point' } } }).text()).not.toContain('rattachée')
  })
})

describe('risques, servitudes et loyers complémentaires', () => {
  it('liste plans de prévention, passé industriel, cavités et arrêtés par type', () => {
    const card = mount(RisksCard, {
      props: {
        data: {
          plans_prevention: [{ nom: 'PPRi-Confluence de Maine', type: 'PPRN-I', en_revision: true }],
          tri: ['Angers - Authion - Saumur'],
          anciens_sites_industriels: {
            rayon_m: 500,
            nb_sites: 27,
            plus_proches: [{ adresse: '17 rue VOLTAIRE', statut: 'Indéterminé', distance_m: 56 }],
          },
          cavites: { rayon_m: 500, nb_cavites: 0, plus_proche: null },
          mouvements_terrain: { rayon_m: 500, nb_evenements: 0 },
          catastrophes_naturelles: {
            nb_arretes: 23,
            par_type: [{ type: 'Inondations', nb_arretes: 15, dernier: 2023 }],
          },
        },
      },
    })
    const text = card.text()
    expect(text).toContain('PPRi-Confluence de Maine (en révision)')
    expect(text).toContain('Angers - Authion - Saumur')
    expect(text).toContain('27 recensés')
    expect(text).toContain('17 rue VOLTAIRE, à 56 m')
    expect(text).toContain('Aucune recensée')
    expect(text).not.toContain('Mouvements de terrain')
    expect(text).toContain('Inondations : 15 (dernier en 2023)')
  })

  it('affiche les servitudes et prescriptions du point', () => {
    const card = mount(ZoningCard, {
      props: {
        data: {
          zones: [],
          servitudes: [{ code: 'AC1', categorie: 'Abords de monument historique', detail: 'Périmètre des abords' }],
          prescriptions: ['Immeuble protégé'],
        },
      },
    })
    expect(card.text()).toContain('Abords de monument historique (AC1, périmètre des abords)')
    expect(card.text()).toContain('Immeuble protégé')
  })

  it('détaille le loyer par typologie quand elle est connue', () => {
    const card = mount(RentCard, {
      props: {
        data: {
          type_bien: 'appartement',
          loyer_m2_charges_comprises: 14.6,
          intervalle_prediction: [11.2, 18.9],
          nb_observations: 29741,
          niveau_prediction: 'commune',
          millesime: 2025,
          par_typologie: { t1_t2: { loyer_m2_charges_comprises: 16.57, nb_observations: 20037 } },
        },
      },
    })
    expect(card.text()).toContain('Appartement de 1 ou 2 pièces16,6 €/m²')
    expect(card.text()).not.toContain('Maison')
  })

  it('reprend bâtiment, servitudes et risques du sol dans le PDF', () => {
    const sections = buildReportSections({
      batiment: ok(BUILDING),
      urbanisme: ok({
        zones: [],
        servitudes: [{ code: 'AC1', categorie: 'Abords de monument historique', detail: null }],
      }),
      georisques: ok({
        plans_prevention: [{ nom: 'PPRi-Confluence de Maine', type: 'PPRN-I', en_revision: true }],
        cavites: { rayon_m: 500, nb_cavites: 2, plus_proche: { type: 'carrière', nom: 'Ardoisière', distance_m: 120 } },
      }),
    })
    const rows = Object.fromEntries(sections.flatMap((section) => section.rows))
    expect(rows['Année de construction du bâtiment']).toBe('1850')
    expect(rows['Copropriété']).toBe('18 lots, immatriculation AC7157225')
    expect(rows['Servitudes d’utilité publique']).toBe('Abords de monument historique (AC1)')
    expect(rows['Plans de prévention des risques (commune)']).toBe('PPRi-Confluence de Maine')
    expect(rows['Cavités souterraines (500 m)']).toBe('2 recensée(s), la plus proche à 120 m')
  })
})

describe('enseignement supérieur', () => {
  const superieur = {
    rayon_m: 3000,
    nb: 7,
    etablissements: [
      { nom: 'Université d’Angers', sigle: 'UA', type: 'Université', secteur: 'public', effectif: 1258, lon: -0.5497, lat: 47.4769, distance_m: 328 },
      { nom: 'ESEO', sigle: 'ESEO', type: 'École', secteur: 'privé', effectif: null, lon: -0.5508, lat: 47.4934, distance_m: 2148 },
    ],
  }

  it('s’ajoute au bloc des établissements scolaires, sans indice de position sociale', async () => {
    const { default: SchoolsCard } = await import('../src/components/cards/SchoolsCard.vue')
    const card = mount(SchoolsCard, {
      props: { data: { rayon_m: 1500, ips_moyen: null, etablissements: [], superieur } },
    })
    const text = card.text().replace(/\s+/g, ' ')
    expect(text).toContain('Aucune école, aucun collège ni lycée dans un rayon de 1,5 km.')
    expect(text).toContain('Enseignement supérieur à moins de 3,0 km')
    expect(text).toContain('Université d’Angers')
    expect(text).toContain('Université public · 1 258 étudiants')
    expect(text).toContain('328 m')
    expect(text).toContain('7 établissements ou implantations au total.')
    expect(text).not.toContain('Indice de position sociale moyen')
  })

  it('apparaît sur la carte avec sa propre couleur', async () => {
    const { mapMarkers } = await import('../src/lib/markers')
    const markers = mapMarkers({ ecoles: ok({ rayon_m: 1500, ips_moyen: null, etablissements: [], superieur }) })
    expect(markers.map((marker) => [marker.kind, marker.label])).toEqual([
      ['superieur', 'Université d’Angers (UA)'],
      ['superieur', 'ESEO (ESEO)'],
    ])
  })
})

describe('zone tendue et collège de secteur dans le tableau de bord', () => {
  it('nomme le collège de secteur sous les établissements, avec sa réserve', async () => {
    const { default: SchoolsCard } = await import('../src/components/cards/SchoolsCard.vue')
    const card = mount(SchoolsCard, {
      props: {
        data: {
          rayon_m: 1500,
          ips_moyen: null,
          etablissements: [],
          college_secteur: {
            statut: 'adresse',
            colleges: [{ uai: '0750465U', nom: 'COLLEGE ALAIN FOURNIER', ips: 104.2, distance_m: 296 }, { uai: '0759999Z' }],
            nb_colleges_commune: 6,
          },
        },
      },
    })
    const text = card.text().replace(/\s+/g, ' ')
    expect(text).toContain('Secteur partagé entre 2 collèges publics')
    expect(text).toContain('COLLEGE ALAIN FOURNIER')
    expect(text).toContain('à 296 m')
    // Collège absent du référentiel des établissements : son identifiant, sans chiffre inventé.
    expect(text).toContain('Collège 0759999Z')
    expect(text).toContain('à confirmer avant tout engagement')
  })

  it('explique la zone tendue et renvoie au simulateur officiel', async () => {
    const { default: RentalMarketCard } = await import('../src/components/cards/RentalMarketCard.vue')
    const card = mount(RentalMarketCard, {
      props: {
        data: {
          occupation: null,
          permis_de_louer: { statut: 'inconnu' },
          zone_tendue: { categorie: 'tendue', tendue: true, reference: 'post décret 22/12/2025' },
        },
      },
    })
    const text = card.text().replace(/\s+/g, ' ')
    expect(text).toContain('Zone tendue')
    expect(text).toContain('Préavis du locataire réduit à un mois')
    expect(text).toContain('post décret 22/12/2025')
    expect(card.find('a').attributes('href')).toBe('https://www.service-public.fr/simulateur/calcul/zones-tendues')
  })
})
