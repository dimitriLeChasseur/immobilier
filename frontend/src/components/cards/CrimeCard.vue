<script setup lang="ts">
import { computed } from 'vue'

import { formatDecimal, formatInteger } from '../../lib/format'
import type { DelinquanceData } from '../../types/audit'

const props = defineProps<{ data: DelinquanceData }>()

// Indicateurs les plus parlants pour un logement, dans l'ordre d'affichage.
const HIGHLIGHTS = [
  'Cambriolages de logement',
  'Vols de véhicule',
  'Vols dans les véhicules',
  'Destructions et dégradations volontaires',
  'Violences physiques hors cadre familial',
  'Vols sans violence contre des personnes',
]

// Variation au-delà de laquelle l'évolution sur un an est signalée.
const TREND_THRESHOLD = 0.1

function trend(rate: number | null, previous: number | null | undefined): string {
  if (rate === null || !previous) return ''
  const change = (rate - previous) / previous
  if (Math.abs(change) < TREND_THRESHOLD) return 'stable sur un an'
  return change > 0 ? 'en hausse sur un an' : 'en baisse sur un an'
}

const hasBenchmarks = computed(() => rows.value.some((row) => row.reperes?.departement != null))

const rows = computed(() =>
  HIGHLIGHTS.map((name) => props.data.indicateurs.find((item) => item.indicateur === name)).filter(
    (item) => item !== undefined,
  ),
)
</script>

<template>
  <table class="w-full text-left text-sm">
    <caption class="mb-2 text-left text-xs text-slate-500">
      Faits enregistrés sur la commune en {{ data.annee }}
    </caption>
    <thead class="text-xs text-slate-500">
      <tr>
        <th scope="col" class="pb-2 font-medium">Indicateur</th>
        <th scope="col" class="pb-2 text-right font-medium">Nombre</th>
        <th scope="col" class="pb-2 text-right font-medium">Pour 1 000 hab.</th>
        <th v-if="hasBenchmarks" scope="col" class="pb-2 text-right font-medium">Département</th>
      </tr>
    </thead>
    <tbody class="divide-y divide-slate-100 tabular-nums">
      <tr v-for="row in rows" :key="row.indicateur">
        <td class="py-2">
          {{ row.indicateur }}
          <span v-if="trend(row.taux_pour_mille, row.reperes?.annee_precedente)" class="block text-xs text-slate-500">
            {{ trend(row.taux_pour_mille, row.reperes?.annee_precedente) }}
          </span>
        </td>
        <template v-if="row.est_diffuse">
          <td class="py-2 text-right">{{ formatInteger(row.nombre) }}</td>
          <td class="py-2 text-right">{{ formatDecimal(row.taux_pour_mille) }}</td>
        </template>
        <td v-else colspan="2" class="py-2 text-right text-xs text-slate-500">Non diffusé (trop peu de faits)</td>
        <td v-if="hasBenchmarks" class="py-2 text-right text-slate-500">
          {{ row.reperes?.departement == null ? '—' : formatDecimal(row.reperes.departement) }}
        </td>
      </tr>
    </tbody>
  </table>
  <p v-if="hasBenchmarks" class="mt-3 text-xs text-slate-500">
    Département : taux pour 1 000 habitants des communes dont la donnée est publiée.
  </p>
</template>
