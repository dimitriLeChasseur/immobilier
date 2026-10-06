import { mount } from '@vue/test-utils'
import { computed } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import CrimeCard from '../src/components/cards/CrimeCard.vue'
import SchoolsCard from '../src/components/cards/SchoolsCard.vue'
import SynthesisPanel from '../src/components/SynthesisPanel.vue'
import { synthesisSections } from '../src/lib/report'
import { LOCKED } from '../src/lib/teaser'
import { UNLOCK_KEY } from '../src/lib/unlock'
import type { ReportSynthesis } from '../src/types/audit'

const FULL: ReportSynthesis = {
  alertes: [{ theme: 'Risques', titre: 'Zone inondable répertoriée', detail: 'Demandez l’état des risques.' }],
  points_forts: [
    { theme: 'Vie de quartier', titre: 'Transports à 4 min à pied', detail: '25 arrêts dans un rayon de 500 m.' },
  ],
}

describe('synthèse en tête de rapport', () => {
  it('affiche les alertes et les points forts avec leur détail', () => {
    const panel = mount(SynthesisPanel, { props: { synthesis: FULL } })
    expect(panel.find('h2').text()).toBe('L’essentiel')
    expect(panel.text()).toContain('Zone inondable répertoriée')
    expect(panel.text()).toContain('25 arrêts dans un rayon de 500 m.')
    expect(panel.find('button').exists()).toBe(false)
  })

  it('en aperçu gratuit, ne montre que les thèmes et propose de débloquer', async () => {
    const open = vi.fn()
    const locked: ReportSynthesis = {
      alertes: [
        { theme: 'Risques', titre: LOCKED, detail: LOCKED },
        { theme: 'Bruit', titre: LOCKED, detail: LOCKED },
      ],
      points_forts: [],
    }
    const panel = mount(SynthesisPanel, {
      props: { synthesis: locked },
      global: { provide: { [UNLOCK_KEY as symbol]: { open, label: computed(() => 'Débloquer l’audit') } } },
    })
    expect(panel.text()).toContain('Points d’attention (2)')
    expect(panel.text()).toContain('Risques')
    expect(panel.text()).not.toContain(LOCKED)
    expect(panel.text()).toContain('Aucun point fort marquant')
    await panel.find('button').trigger('click')
    expect(open).toHaveBeenCalledOnce()
  })

  it('ouvre le PDF par la synthèse, alertes d’abord', () => {
    expect(synthesisSections(FULL)).toEqual([
      {
        title: 'L’essentiel',
        rows: [
          ['Attention · Risques', 'Zone inondable répertoriée. Demandez l’état des risques.'],
          ['Point fort · Vie de quartier', 'Transports à 4 min à pied. 25 arrêts dans un rayon de 500 m.'],
        ],
      },
    ])
    expect(synthesisSections(null)).toEqual([])
    expect(synthesisSections({ alertes: [], points_forts: [] })).toEqual([])
  })
})

describe('repères de comparaison', () => {
  it('situe la délinquance face au département et à l’année précédente', () => {
    const card = mount(CrimeCard, {
      props: {
        data: {
          annee: 2025,
          indicateurs: [
            {
              indicateur: 'Cambriolages de logement',
              unite_de_compte: 'Infraction',
              est_diffuse: true,
              nombre: 156,
              taux_pour_mille: 1.7,
              reperes: { departement: 1.97, national: 3.27, annee_precedente: 2.3 },
            },
          ],
        },
      },
    })
    expect(card.text()).toContain('Département')
    expect(card.text()).toContain('2,0')
    expect(card.text()).toContain('en baisse sur un an')
  })

  it('reste lisible sans repère (rapport ancien)', () => {
    const card = mount(CrimeCard, {
      props: {
        data: {
          annee: 2025,
          indicateurs: [
            {
              indicateur: 'Cambriolages de logement',
              unite_de_compte: 'Infraction',
              est_diffuse: true,
              nombre: 156,
              taux_pour_mille: 1.7,
            },
          ],
        },
      },
    })
    expect(card.text()).not.toContain('Département')
    expect(card.text()).not.toContain('sur un an')
  })

  it('donne l’IPS par niveau face à la moyenne nationale', () => {
    const card = mount(SchoolsCard, {
      props: {
        data: {
          rayon_m: 1500,
          ips_moyen: 124.2,
          par_type: {
            ecole: { nb: 8, ips_moyen: 120.8, moyenne_departement: 105.4, moyenne_nationale: 104.8 },
            lycee: { nb: 1, ips_moyen: 129.9, moyenne_departement: 110.5, moyenne_nationale: null },
          },
          etablissements: [],
        },
      },
    })
    expect(card.text()).toContain('IPS moyen, écoles')
    expect(card.text()).toContain('8 établissements · France : 104,8')
    expect(card.text()).toContain('1 établissement')
    expect(card.text()).not.toContain('IPS moyen, collèges')
  })
})
