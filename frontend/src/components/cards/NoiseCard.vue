<script setup lang="ts">
import { computed } from 'vue'

import type { BruitData } from '../../types/audit'
import StatTile from '../StatTile.vue'

const props = defineProps<{ data: BruitData }>()

const STRONG_DB = 65
const INFRASTRUCTURES = { route: 'Route', fer: 'Voie ferrée', air: 'Aéroport', industrie: 'Industrie' } as const

const tone = computed(() => {
  const level = props.data.niveau_max_db
  if (level === null) return 'good'
  return level >= STRONG_DB ? 'bad' : 'warn'
})
const headline = computed(() => {
  const strongest = props.data.sources[0]
  if (!strongest) return 'Moins de 55 dB'
  return strongest.db_max === null ? `Plus de ${strongest.db_min} dB` : `${strongest.db_min} à ${strongest.db_max} dB`
})
</script>

<template>
  <StatTile label="Niveau moyen sur 24 h (Lden)" :value="headline" :tone="tone" />
  <p class="mt-3 text-sm text-slate-600">{{ data.message }}</p>
  <dl v-if="data.sources.length" class="mt-3 space-y-1 text-sm">
    <div v-for="source in data.sources" :key="source.infrastructure" class="flex justify-between">
      <dt class="text-slate-500">{{ INFRASTRUCTURES[source.infrastructure] }}</dt>
      <dd class="tabular-nums">
        {{ source.db_max === null ? `plus de ${source.db_min}` : `${source.db_min} à ${source.db_max}` }} dB(A)
      </dd>
    </div>
  </dl>
  <p class="mt-3 text-xs text-slate-500">
    Cartes de bruit stratégiques des grandes routes et voies ferrées. Les rues ordinaires et le
    voisinage n’y figurent pas.
  </p>
</template>
