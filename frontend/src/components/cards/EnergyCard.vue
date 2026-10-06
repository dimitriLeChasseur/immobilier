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

// Le rayon affiché est celui que l'échantillon couvre vraiment, pas le rayon demandé.
const hint = computed(() => {
  const { nb_dpe_analyses: analysed, nb_dpe_total: total, rayon_m: radius, rayon_effectif_m: reach } = props.data
  const sample = `${formatInteger(analysed)} diagnostics`
  if (props.data.perimetre === 'rue') return `${sample} rattachés aux numéros de la rue`
  if (total === null || total <= analysed) return `${sample} analysés à moins de ${reach ?? radius} m`
  return `${sample} les plus proches, à moins de ${reach ?? radius} m (${formatInteger(total)} recensés dans ${radius} m)`
})

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
    :hint="hint"
  />
  <p
    v-if="data.analyse?.message"
    class="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-900"
  >
    {{ data.analyse.message }}
  </p>
  <details v-if="data.par_numero?.length" class="mt-3 text-sm">
    <summary class="cursor-pointer font-medium text-brand-700">Détail par numéro de la rue</summary>
    <ul class="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 tabular-nums sm:grid-cols-3">
      <li v-for="entry in data.par_numero" :key="entry.numero" class="flex justify-between gap-2">
        <span class="text-slate-600">
          N° {{ entry.numero }}<template v-if="entry.annee_construction"> ({{ entry.annee_construction }})</template>
        </span>
        <span class="font-medium text-slate-900">{{ entry.etiquette_dominante ?? '—' }} · {{ entry.nb_dpe }}</span>
      </li>
    </ul>
    <p class="mt-2 text-xs text-slate-500">Étiquette la plus fréquente et nombre de diagnostics par numéro.</p>
  </details>
  <div class="mt-4">
    <BaseChart :config="chart" label="Répartition des étiquettes énergie des logements voisins" />
  </div>
</template>
