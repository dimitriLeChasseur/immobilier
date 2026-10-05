<script setup lang="ts">
import type { ChartConfiguration } from 'chart.js'
import { computed } from 'vue'

import { formatInteger } from '../../lib/format'
import type { DpeData } from '../../types/audit'
import BaseChart from '../BaseChart.vue'
import StatTile from '../StatTile.vue'

const props = defineProps<{ data: DpeData }>()

// Couleurs réglementaires de l'étiquette énergie.
const LABEL_COLORS: Record<string, string> = {
  A: '#319834',
  B: '#33cc31',
  C: '#cbfc34',
  D: '#fbfe06',
  E: '#fbcc05',
  F: '#fc9935',
  G: '#fc0205',
}
const LABELS = Object.keys(LABEL_COLORS)

const chart = computed<ChartConfiguration>(() => ({
  type: 'bar',
  data: {
    labels: LABELS,
    datasets: [
      {
        label: 'Nombre de logements',
        data: LABELS.map((label) => props.data.repartition_dpe[label] ?? 0),
        backgroundColor: LABELS.map((label) => LABEL_COLORS[label] ?? '#94a3b8'),
        borderRadius: 6,
      },
    ],
  },
  options: { scales: { y: { ticks: { precision: 0 } } } },
}))
</script>

<template>
  <StatTile
    label="Étiquette la plus fréquente"
    :value="data.etiquette_dominante ?? '—'"
    :hint="`${formatInteger(data.nb_dpe_analyses)} diagnostics analysés à moins de ${data.rayon_m} m`"
  />
  <p
    v-if="data.analyse?.message"
    class="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-900"
  >
    {{ data.analyse.message }}
  </p>
  <div class="mt-4">
    <BaseChart :config="chart" label="Répartition des étiquettes énergie des logements voisins" />
  </div>
</template>
