<script setup lang="ts">
import { computed } from 'vue'

import { episodesNotice } from '../../lib/air'
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

// L'indice du jour manque quand la région ne l'a pas publié : les épisodes restent.
const index = computed(() => (props.data.indice === undefined ? null : props.data))
const tone = computed(() => {
  const level = index.value?.indice ?? 0
  if (level >= BAD_FROM) return 'bad'
  return level >= WATCH_FROM ? 'warn' : 'good'
})
const levels = computed(() => {
  const subIndices = index.value?.sous_indices
  if (!subIndices) return []
  return (Object.keys(POLLUTANTS) as (keyof typeof POLLUTANTS)[])
    .map((key) => ({ label: POLLUTANTS[key], level: subIndices[key] }))
    .filter((entry) => entry.level !== null)
})
const zone = computed(() =>
  index.value?.zone.type === 'epci' ? `l’intercommunalité (${index.value.zone.nom})` : 'la commune',
)
const episodes = computed(() => (props.data.episodes ? episodesNotice(props.data.episodes) : null))
</script>

<template>
  <template v-if="index">
    <StatTile
      :label="`Indice ATMO du ${formatDate(index.date)}`"
      :value="index.qualificatif"
      :tone="tone"
      :hint="`Niveau ${index.indice} sur 6 (1 = bon, 6 = extrêmement mauvais)`"
    />
    <p v-if="index.polluants_dominants.length" class="mt-3 text-sm text-slate-600">
      Déterminé par : {{ index.polluants_dominants.join(', ') }}.
    </p>
    <dl v-if="levels.length" class="mt-3 space-y-1 text-sm">
      <div v-for="entry in levels" :key="entry.label" class="flex justify-between">
        <dt class="text-slate-500">{{ entry.label }}</dt>
        <dd class="tabular-nums">{{ entry.level }} / 6</dd>
      </div>
    </dl>
    <p v-if="index.demain" class="mt-3 text-sm text-slate-600">
      Prévision pour demain : {{ index.demain.qualificatif.toLowerCase() }} ({{ index.demain.indice }} / 6).
    </p>
    <p class="mt-3 text-xs text-slate-500">
      Indice du jour calculé pour {{ zone }} : il varie d’un jour à l’autre et ne résume pas l’année.
      Source : {{ index.producteur }}, Atmo France.
    </p>
  </template>
  <p v-else class="text-sm text-slate-500">Indice ATMO non publié pour cette commune aujourd’hui.</p>

  <div v-if="episodes" class="mt-4 rounded-xl bg-slate-100 px-3 py-2 text-slate-700">
    <p class="text-sm font-medium">{{ episodes.title }}</p>
    <ul v-if="episodes.lines.length" class="mt-1 space-y-0.5 text-sm">
      <li v-for="line in episodes.lines" :key="line">{{ line }}</li>
    </ul>
    <p class="mt-1 text-xs">{{ episodes.detail }}</p>
  </div>
  <p v-else class="mt-4 text-xs text-slate-500">Historique des épisodes de pollution momentanément indisponible.</p>
</template>
