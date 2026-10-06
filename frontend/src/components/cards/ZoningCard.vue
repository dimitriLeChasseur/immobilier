<script setup lang="ts">
import { formatDate } from '../../lib/format'
import type { UrbanismeData } from '../../types/audit'

defineProps<{ data: UrbanismeData }>()

const ZONE_TYPES: Record<string, string> = {
  U: 'Zone urbaine',
  AUc: 'Zone à urbaniser (ouverte)',
  AUs: 'Zone à urbaniser (fermée)',
  A: 'Zone agricole',
  N: 'Zone naturelle',
}
</script>

<template>
  <ul class="space-y-3">
    <li v-for="zone in data.zones" :key="`${zone.document}-${zone.libelle}`">
      <p class="flex items-baseline gap-2">
        <span class="rounded-md bg-slate-900 px-2 py-0.5 text-sm font-semibold text-white">{{ zone.libelle }}</span>
        <span class="text-sm font-medium text-slate-900">
          {{ ZONE_TYPES[zone.type_zone ?? ''] ?? zone.type_zone }}
        </span>
      </p>
      <p v-if="zone.libelle_long" class="mt-1 text-sm text-slate-600">{{ zone.libelle_long }}</p>
      <p class="mt-1 text-xs text-slate-500">Document validé le {{ formatDate(zone.date_validation) }}</p>
    </li>
  </ul>
  <div v-if="data.servitudes?.length" class="mt-4">
    <h4 class="text-xs font-medium tracking-wide text-slate-500 uppercase">Servitudes d’utilité publique</h4>
    <ul class="mt-2 space-y-1 text-sm">
      <li v-for="item in data.servitudes" :key="`${item.code}-${item.detail}`">
        <span class="font-medium text-slate-900">{{ item.categorie }}</span>
        <span class="text-slate-500"> ({{ item.code }}<template v-if="item.detail">, {{ item.detail.toLowerCase() }}</template>)</span>
      </li>
    </ul>
  </div>
  <div v-if="data.prescriptions?.length" class="mt-4">
    <h4 class="text-xs font-medium tracking-wide text-slate-500 uppercase">Prescriptions du document d’urbanisme</h4>
    <ul class="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
      <li v-for="item in data.prescriptions" :key="item">{{ item }}</li>
    </ul>
  </div>
  <p v-if="data.servitudes?.length || data.prescriptions?.length" class="mt-3 text-xs text-slate-500">
    Relevées au point audité sur le Géoportail de l’urbanisme : elles peuvent limiter les travaux ou la
    constructibilité.
  </p>
</template>
