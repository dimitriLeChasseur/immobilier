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
