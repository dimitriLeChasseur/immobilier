<script setup lang="ts">
import { computed } from 'vue'

import { formatDistance, formatInteger } from '../../lib/format'
import { riskIndicators, type Tone } from '../../lib/insights'
import type { GeorisquesData } from '../../types/audit'

const props = defineProps<{ data: GeorisquesData }>()

const TONE_CLASSES: Record<Tone, string> = {
  good: 'bg-emerald-50 text-emerald-800',
  warn: 'bg-amber-50 text-amber-800',
  bad: 'bg-rose-50 text-rose-800',
  neutral: 'bg-slate-100 text-slate-600',
}

const indicators = computed(() => riskIndicators(props.data))
</script>

<template>
  <ul class="grid gap-2 sm:grid-cols-2">
    <li
      v-for="indicator in indicators"
      :key="indicator.label"
      class="rounded-xl px-3 py-2"
      :class="TONE_CLASSES[indicator.tone]"
    >
      <p class="text-xs opacity-80">{{ indicator.label }}</p>
      <p class="text-sm font-medium">{{ indicator.value }}</p>
      <p v-if="indicator.advice" class="mt-1 text-xs opacity-90">{{ indicator.advice }}</p>
    </li>
  </ul>

  <dl class="mt-4 space-y-2 text-sm">
    <div v-if="data.seveso">
      <dt class="text-slate-500">Sites Seveso à moins de {{ formatDistance(data.seveso.rayon_m) }}</dt>
      <dd v-if="data.seveso.sites.length">
        <span v-for="site in data.seveso.sites" :key="`${site.nom}-${site.distance_m}`" class="block">
          {{ site.nom }} — {{ site.statut }}, à {{ formatDistance(site.distance_m) }}
        </span>
      </dd>
      <dd v-else>Aucun site recensé</dd>
      <dd v-if="data.seveso.liste_tronquee" class="text-xs text-amber-700">
        Zone très dense en installations classées : cette liste peut être incomplète.
      </dd>
    </div>
    <div v-if="data.catastrophes_naturelles">
      <dt class="text-slate-500">Arrêtés de catastrophe naturelle sur la commune</dt>
      <dd>{{ formatInteger(data.catastrophes_naturelles.nb_arretes) }}</dd>
    </div>
    <div v-if="data.risques?.length">
      <dt class="text-slate-500">Risques recensés sur la commune</dt>
      <dd>{{ data.risques.join(', ') }}</dd>
    </div>
  </dl>
</template>
