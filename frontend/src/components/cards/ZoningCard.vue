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
</template>
