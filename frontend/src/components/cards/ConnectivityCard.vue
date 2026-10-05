<script setup lang="ts">
import { computed } from 'vue'

import { formatDate, formatInteger, formatPercent } from '../../lib/format'
import type { ConnectiviteData } from '../../types/audit'
import StatTile from '../StatTile.vue'

const props = defineProps<{ data: ConnectiviteData }>()

const GOOD_COVERAGE_PCT = 95
const FAIR_COVERAGE_PCT = 80

const tone = computed(() => {
  const share = props.data.part_fibre_pct
  if (share === null) return 'default'
  if (share >= GOOD_COVERAGE_PCT) return 'good'
  return share >= FAIR_COVERAGE_PCT ? 'warn' : 'bad'
})
</script>

<template>
  <StatTile
    label="Locaux raccordables à la fibre"
    :value="formatPercent(data.part_fibre_pct)"
    :tone="tone"
    :hint="`sur ${formatInteger(data.nb_locaux)} locaux de la commune`"
  />
  <dl class="mt-3 space-y-1 text-sm">
    <div class="flex justify-between">
      <dt class="text-slate-500">Câble</dt>
      <dd class="tabular-nums">{{ formatPercent(data.part_cable_pct) }}</dd>
    </div>
    <div class="flex justify-between">
      <dt class="text-slate-500">4G fixe (box 4G)</dt>
      <dd class="tabular-nums">{{ formatPercent(data.part_4g_fixe_pct) }}</dd>
    </div>
  </dl>
  <p class="mt-3 text-xs text-slate-500">
    Moyenne communale au {{ formatDate(data.date_donnees) }} : elle ne garantit pas l’éligibilité de
    cette adresse précise, à confirmer sur maconnexioninternet.arcep.fr.
  </p>
</template>
