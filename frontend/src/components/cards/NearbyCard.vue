<script setup lang="ts">
import { formatInteger } from '../../lib/format'
import { orderedCategories, POI_CATEGORY_LABELS } from '../../lib/sources'
import type { ProximiteData } from '../../types/audit'

defineProps<{ data: ProximiteData }>()

</script>

<template>
  <ul class="divide-y divide-slate-100 text-sm">
    <li v-for="[key, category] in orderedCategories(data.categories)" :key="key" class="flex items-center justify-between gap-4 py-2">
      <div class="min-w-0">
        <p class="font-medium text-slate-900">{{ POI_CATEGORY_LABELS[key] ?? key }}</p>
        <p v-if="category.plus_proche" class="truncate text-xs text-slate-500">
          {{ category.plus_proche.nom ?? 'Le plus proche' }} à {{ category.plus_proche.marche_min }} min
        </p>
        <p v-else class="text-xs text-slate-500">Rien à moins de {{ data.rayon_m }} m</p>
      </div>
      <span class="shrink-0 rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium tabular-nums text-slate-700">
        {{ formatInteger(category.nb) }}
      </span>
    </li>
  </ul>
  <p class="mt-3 text-xs text-slate-500">
    Dans un rayon de {{ data.rayon_m }} m.
    <template v-if="data.methode_temps === 'itineraire_pieton'">Temps de marche calculés sur itinéraire piéton.</template>
    <template v-else>Temps de marche estimés à vol d’oiseau.</template>
  </p>
</template>
