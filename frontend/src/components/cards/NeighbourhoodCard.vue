<script setup lang="ts">
import { computed } from 'vue'

import { formatEuros, formatInteger, formatPercent } from '../../lib/format'
import { districtNotice, incomeGap, incomeRange, populationTrend } from '../../lib/neighbourhood'
import type { QuartierData } from '../../types/audit'
import StatTile from '../StatTile.vue'

const props = defineProps<{ data: QuartierData }>()

const income = computed(() => props.data.revenus)
const district = computed(() => districtNotice(props.data.quartier_prioritaire))
const trend = computed(() => populationTrend(props.data.population))
const quarter = computed(() => props.data.iris?.nom ?? props.data.iris?.code ?? null)
</script>

<template>
  <div class="grid grid-cols-1 gap-6 sm:grid-cols-2">
    <div v-if="income">
      <div class="flex flex-wrap gap-x-8 gap-y-3">
        <StatTile
          label="Niveau de vie médian"
          :value="formatEuros(income.revenu_median)"
          hint="par an et par unité de consommation"
        />
        <StatTile label="Taux de pauvreté" :value="formatPercent(income.taux_pauvrete_pct, 0)" />
      </div>
      <p v-if="incomeGap(income)" class="mt-3 text-sm text-slate-700">Niveau de vie {{ incomeGap(income) }}.</p>
      <p v-if="incomeRange(income)" class="mt-1 text-sm text-slate-700">{{ incomeRange(income) }}.</p>
      <p class="mt-3 text-xs text-slate-500">
        Quartier « {{ quarter }} », revenus disponibles {{ income.annee }} (INSEE, Filosofi)<template
          v-if="income.reference_nationale"
        >
          ; taux de pauvreté national : {{ formatPercent(income.reference_nationale.taux_pauvrete_pct) }}</template
        >. Le niveau de vie est le revenu après impôts et prestations, rapporté à la taille du ménage.
      </p>
    </div>
    <p v-else class="text-sm text-slate-500">
      L’INSEE ne diffuse pas les revenus à l’échelle de ce quartier<template v-if="quarter"> (« {{ quarter }} »)</template
      > : ils ne sont publiés que pour les quartiers des communes les plus peuplées.
    </p>

    <div class="space-y-3">
      <div v-if="district" class="rounded-xl bg-slate-100 px-3 py-2 text-slate-700">
        <p class="text-sm font-medium">{{ district.title }}</p>
        <p class="mt-1 text-xs">{{ district.detail }}</p>
      </div>
      <div v-if="data.population" class="rounded-xl bg-slate-100 px-3 py-2 text-slate-700">
        <p class="text-sm font-medium">
          {{ formatInteger(data.population.habitants) }} habitants<template v-if="trend"> · {{ trend }}</template>
        </p>
        <p class="mt-1 text-xs">
          Population {{ data.population.arrondissement ? 'de l’arrondissement' : 'de la commune' }} au recensement
          {{ data.population.annee }}. Une population qui progresse soutient la demande de logements ; une
          population qui recule la détend.
        </p>
      </div>
    </div>
  </div>
</template>
