<script setup lang="ts">
import type { ChartConfiguration } from 'chart.js'
import { computed } from 'vue'

import { capitalize, formatDate, formatDistance, formatEuros, formatInteger, formatPricePerM2 } from '../../lib/format'
import type { DvfData } from '../../types/audit'
import BaseChart from '../BaseChart.vue'
import StatTile from '../StatTile.vue'

const props = defineProps<{ data: DvfData }>()

const VISIBLE_SALES = 5

const chart = computed<ChartConfiguration>(() => ({
  type: 'bar',
  data: {
    labels: props.data.historique.map((year) => String(year.annee)),
    datasets: [
      {
        label: 'Prix médian au m²',
        data: props.data.historique.map((year) => year.prix_m2_median),
        backgroundColor: '#14b8a6',
        borderRadius: 6,
      },
    ],
  },
  options: {
    scales: { y: { ticks: { callback: (value) => `${formatInteger(Number(value))} €` } } },
    plugins: {
      tooltip: {
        callbacks: {
          label: (item) => formatPricePerM2(Number(item.raw)),
          afterLabel: (item) => `${props.data.historique[item.dataIndex]?.nb_ventes ?? 0} ventes`,
        },
      },
    },
  },
}))
</script>

<template>
  <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
    <div class="min-w-0">
      <div class="mb-4 flex flex-wrap gap-x-8 gap-y-3">
        <StatTile
          label="Prix médian"
          :value="formatPricePerM2(data.prix_m2_median)"
          :hint="`${formatInteger(data.nb_ventes)} ventes à moins de ${data.rayon_m} m`"
        />
        <StatTile
          v-for="(stats, kind) in data.par_type"
          :key="kind"
          :label="capitalize(String(kind))"
          :value="formatPricePerM2(stats.prix_m2_median)"
          :hint="`${formatInteger(stats.nb_ventes)} ventes`"
        />
      </div>
      <p class="mb-3 text-sm text-slate-600">
        La moitié des ventes s’est conclue entre
        <strong class="font-semibold text-slate-900">{{ formatPricePerM2(data.dispersion.q1) }}</strong> et
        <strong class="font-semibold text-slate-900">{{ formatPricePerM2(data.dispersion.q3) }}</strong>
        (extrêmes : {{ formatInteger(data.dispersion.min) }} à {{ formatInteger(data.dispersion.max) }} €/m²).
      </p>
      <BaseChart :config="chart" label="Prix médian au m² par année" />
    </div>

    <div class="min-w-0">
      <h4 class="mb-2 text-xs font-medium tracking-wide text-slate-500 uppercase">Dernières ventes</h4>
      <div class="overflow-x-auto">
        <table class="w-full text-left text-sm">
          <thead class="text-xs text-slate-500">
            <tr>
              <th scope="col" class="pb-2 font-medium">Date</th>
              <th scope="col" class="pb-2 font-medium">Bien</th>
              <th scope="col" class="pb-2 text-right font-medium">Prix</th>
              <th scope="col" class="pb-2 text-right font-medium">€/m²</th>
              <th scope="col" class="pb-2 text-right font-medium">Distance</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 tabular-nums">
            <tr v-for="sale in data.dernieres_ventes.slice(0, VISIBLE_SALES)" :key="`${sale.date}-${sale.prix}-${sale.distance_m}`">
              <td class="py-2 whitespace-nowrap">{{ formatDate(sale.date) }}</td>
              <td class="py-2">
                {{ capitalize(sale.type) }}, {{ formatInteger(sale.surface_m2) }} m²<template v-if="sale.pieces">, {{ sale.pieces }} p.</template>
              </td>
              <td class="py-2 text-right">{{ formatEuros(sale.prix) }}</td>
              <td class="py-2 text-right">{{ formatInteger(sale.prix_m2) }}</td>
              <td class="py-2 text-right">{{ formatDistance(sale.distance_m) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="mt-3 text-xs text-slate-500">
        Les écarts entre biens voisins sont normaux : le fichier des ventes ne connaît ni l’étage, ni
        l’état du logement, ni son étiquette énergie, qui pèsent fortement sur le prix.
      </p>
    </div>
  </div>
</template>
