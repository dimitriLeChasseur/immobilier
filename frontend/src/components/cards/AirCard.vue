<script setup lang="ts">
import { computed } from 'vue'

import { formatDate } from '../../lib/format'
import type { QualiteAirData } from '../../types/audit'
import StatTile from '../StatTile.vue'

const props = defineProps<{ data: QualiteAirData }>()

// Indice ATMO : 1 et 2 favorables, 3 à surveiller, 4 et plus défavorables.
const WATCH_FROM = 3
const BAD_FROM = 4
const POLLUTANTS = {
  pm2_5: 'Particules PM2.5',
  pm10: 'Particules PM10',
  no2: 'Dioxyde d’azote',
  o3: 'Ozone',
  so2: 'Dioxyde de soufre',
} as const

const tone = computed(() => {
  if (props.data.indice >= BAD_FROM) return 'bad'
  return props.data.indice >= WATCH_FROM ? 'warn' : 'good'
})
const levels = computed(() =>
  (Object.keys(POLLUTANTS) as (keyof typeof POLLUTANTS)[])
    .map((key) => ({ label: POLLUTANTS[key], level: props.data.sous_indices[key] }))
    .filter((entry) => entry.level !== null),
)
const zone = computed(() =>
  props.data.zone.type === 'epci' ? `l’intercommunalité (${props.data.zone.nom})` : 'la commune',
)
</script>

<template>
  <StatTile
    :label="`Indice ATMO du ${formatDate(data.date)}`"
    :value="data.qualificatif"
    :tone="tone"
    :hint="`Niveau ${data.indice} sur 6 (1 = bon, 6 = extrêmement mauvais)`"
  />
  <p v-if="data.polluants_dominants.length" class="mt-3 text-sm text-slate-600">
    Déterminé par : {{ data.polluants_dominants.join(', ') }}.
  </p>
  <dl v-if="levels.length" class="mt-3 space-y-1 text-sm">
    <div v-for="entry in levels" :key="entry.label" class="flex justify-between">
      <dt class="text-slate-500">{{ entry.label }}</dt>
      <dd class="tabular-nums">{{ entry.level }} / 6</dd>
    </div>
  </dl>
  <p v-if="data.demain" class="mt-3 text-sm text-slate-600">
    Prévision pour demain : {{ data.demain.qualificatif.toLowerCase() }} ({{ data.demain.indice }} / 6).
  </p>
  <p class="mt-3 text-xs text-slate-500">
    Indice du jour calculé pour {{ zone }} : il varie d’un jour à l’autre et ne résume pas l’année.
    Source : {{ data.producteur }}, Atmo France.
  </p>
</template>
