<script setup lang="ts">
import { formatDecimal, formatDistance } from '../../lib/format'
import { SCHOOL_KIND_LABELS } from '../../lib/sources'
import type { EcolesData } from '../../types/audit'
import StatTile from '../StatTile.vue'

defineProps<{ data: EcolesData }>()

const VISIBLE_SCHOOLS = 6
</script>

<template>
  <StatTile
    label="Indice de position sociale moyen"
    :value="formatDecimal(data.ips_moyen)"
    :hint="`${data.etablissements.length} établissements les plus proches · moyenne nationale ≈ 100`"
  />
  <ul class="mt-3 divide-y divide-slate-100 text-sm">
    <li
      v-for="school in data.etablissements.slice(0, VISIBLE_SCHOOLS)"
      :key="school.uai"
      class="flex items-center justify-between gap-4 py-2"
    >
      <div class="min-w-0">
        <p class="truncate font-medium text-slate-900">{{ school.nom }}</p>
        <p class="text-xs text-slate-500">
          {{ SCHOOL_KIND_LABELS[school.type_etablissement] }} {{ school.secteur === 'prive' ? 'privé' : 'public' }} ·
          à {{ formatDistance(school.distance_m) }}
        </p>
      </div>
      <span class="shrink-0 text-sm font-semibold tabular-nums text-slate-900">{{ formatDecimal(school.ips) }}</span>
    </li>
  </ul>
</template>
