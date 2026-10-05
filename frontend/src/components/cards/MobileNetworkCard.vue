<script setup lang="ts">
import { formatDistance, formatInteger } from '../../lib/format'
import type { ReseauMobileData } from '../../types/audit'

defineProps<{ data: ReseauMobileData }>()

const GENERATION_CLASSES: Record<string, string> = {
  '5G': 'bg-brand-600 text-white',
  '4G': 'bg-brand-100 text-brand-900',
}
</script>

<template>
  <p class="mb-3 text-sm text-slate-600">
    {{ formatInteger(data.nb_sites) }} {{ data.nb_sites > 1 ? 'sites d’antennes actifs' : 'site d’antennes actif' }}
    à moins de {{ formatDistance(data.rayon_m) }}.
    <template v-if="data.operateurs_5g.length">5G déployée par {{ data.operateurs_5g.join(', ') }}.</template>
    <template v-else>Aucune antenne 5G à proximité.</template>
  </p>
  <ul class="divide-y divide-slate-100 text-sm">
    <li v-for="operator in data.operateurs" :key="operator.nom" class="flex items-center justify-between gap-3 py-2">
      <div class="min-w-0">
        <p class="font-medium text-slate-900">{{ operator.nom }}</p>
        <p class="text-xs text-slate-500">
          {{ operator.nb_sites }} site(s), le plus proche à {{ formatDistance(operator.site_le_plus_proche_m) }}
        </p>
      </div>
      <ul class="flex shrink-0 gap-1" :aria-label="`Générations disponibles chez ${operator.nom}`">
        <li
          v-for="generation in operator.generations"
          :key="generation"
          class="rounded-md px-1.5 py-0.5 text-xs font-semibold"
          :class="GENERATION_CLASSES[generation] ?? 'bg-slate-100 text-slate-600'"
        >
          {{ generation }}
        </li>
      </ul>
    </li>
  </ul>
  <p class="mt-3 text-xs text-slate-500">
    Antennes déclarées à l’ANFR : leur présence indique un réseau disponible, pas la qualité de
    réception à l’intérieur du logement.
    <template v-if="data.liste_tronquee">Zone très dense : liste partielle.</template>
  </p>
</template>
