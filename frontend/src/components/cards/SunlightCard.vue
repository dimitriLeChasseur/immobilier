<script setup lang="ts">
import type { ChartConfiguration } from 'chart.js'
import { computed } from 'vue'

import { formatInteger } from '../../lib/format'
import type { EnsoleillementData } from '../../types/audit'
import BaseChart from '../BaseChart.vue'
import StatTile from '../StatTile.vue'

const props = defineProps<{ data: EnsoleillementData }>()

// Ordre de la rose des vents, imposé ici : un rapport relu depuis le cache ne conserve pas
// l'ordre des clés envoyé par le serveur.
const COMPASS = ['N', 'NE', 'E', 'SE', 'S', 'SO', 'O', 'NO'] as const

const chart = computed<ChartConfiguration>(() => ({
  type: 'radar',
  data: {
    labels: [...COMPASS],
    datasets: [
      {
        label: 'Hauteur du relief (°)',
        data: COMPASS.map((direction) => props.data.masque_relief_deg[direction] ?? 0),
        backgroundColor: 'rgb(245 158 11 / 0.25)',
        borderColor: '#d97706',
        borderWidth: 2,
        pointRadius: 2,
      },
    ],
  },
  options: { scales: { r: { beginAtZero: true, suggestedMax: 10, ticks: { display: false } } } },
}))
</script>

<template>
  <div class="flex flex-wrap gap-x-8 gap-y-3">
    <StatTile label="Sur l’année" :value="`${data.score.annuel} %`" hint="du temps de jour sans masque" />
    <StatTile label="Au solstice d’hiver" :value="`${data.score.solstice_hiver} %`" />
  </div>
  <p v-if="data.synthese" class="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-900">
    {{ data.synthese }}
  </p>
  <div class="mt-4">
    <BaseChart :config="chart" label="Hauteur du relief à l’horizon, par direction" />
  </div>
  <p class="mt-3 text-xs text-slate-500">
    Altitude {{ formatInteger(data.altitude_m) }} m. Seul le relief est pris en compte : l’ombre des
    bâtiments voisins n’est pas calculée.
  </p>
</template>
