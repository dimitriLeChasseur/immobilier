<script setup lang="ts">
import { computed } from 'vue'

import { climateRows, energyRows } from '../../lib/air'
import type { ClimatAirEnergieData } from '../../types/audit'

const props = defineProps<{ data: ClimatAirEnergieData }>()

const emissions = computed(() => climateRows(props.data))
const energies = computed(() => energyRows(props.data))
</script>

<template>
  <p class="text-sm text-slate-700">
    Ce qu’émet et consomme en un an l’intercommunalité <strong>{{ data.territoire.nom }}</strong>, et non l’adresse
    elle-même.
  </p>
  <dl v-if="emissions.length" class="mt-3 space-y-2 text-sm">
    <div v-for="[label, value] in emissions" :key="label">
      <dt class="font-medium text-slate-900">{{ label }}</dt>
      <dd class="text-slate-700">{{ value }}</dd>
    </div>
  </dl>
  <table v-if="energies.length" class="mt-4 w-full text-sm">
    <caption class="mb-1 text-left font-medium text-slate-900">Énergie des logements et des bureaux</caption>
    <thead>
      <tr class="text-xs text-slate-500">
        <th scope="col" class="text-left font-normal">Énergie</th>
        <th scope="col" class="text-right font-normal">Territoire</th>
        <th v-if="data.repere" scope="col" class="text-right font-normal">{{ data.repere.territoire }}</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="row in energies" :key="row.label">
        <th scope="row" class="text-left font-normal text-slate-700">{{ row.label }}</th>
        <td class="text-right tabular-nums">{{ row.local }}</td>
        <td v-if="data.repere" class="text-right tabular-nums text-slate-500">{{ row.reference }}</td>
      </tr>
    </tbody>
  </table>
  <p class="mt-3 text-xs text-slate-500">
    Inventaire {{ data.millesime }}<template v-if="data.version_inventaire"> (version {{ data.version_inventaire }})</template>,
    produit par {{ data.producteur ?? 'l’association régionale de surveillance de l’air' }} et publié par Atmo France.
    <template v-if="data.repere">Repère : {{ data.repere.territoire }}, inventaire {{ data.repere.millesime }}.</template>
  </p>
</template>
