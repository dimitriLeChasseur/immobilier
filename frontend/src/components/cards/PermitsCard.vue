<script setup lang="ts">
import { formatDate, formatDistance, formatInteger } from '../../lib/format'
import type { PermisData } from '../../types/audit'

defineProps<{ data: PermisData }>()

const VISIBLE_PERMITS = 4
const STATES: Record<string, string> = { autorise: 'Autorisé', commence: 'Chantier ouvert' }
</script>

<template>
  <p
    class="mb-3 rounded-xl px-3 py-2 text-sm font-medium"
    :class="data.risque_vis_a_vis ? 'bg-amber-50 text-amber-800' : 'bg-emerald-50 text-emerald-800'"
  >
    <template v-if="data.risque_vis_a_vis">
      {{ data.nb_projets_a_risque }} projet(s) de 3 niveaux ou plus à moins de 60 m : vis-à-vis possible.
    </template>
    <template v-else>Aucun projet de grande hauteur détecté à moins de 60 m.</template>
  </p>
  <p class="mb-2 text-xs text-slate-500">
    {{ formatInteger(data.nb_permis) }} autorisation(s) en cours à moins de {{ data.rayon_m }} m
  </p>
  <ul class="divide-y divide-slate-100 text-sm">
    <li v-for="permit in data.permis.slice(0, VISIBLE_PERMITS)" :key="permit.num_permis" class="py-2">
      <p class="font-medium text-slate-900">{{ permit.adresse }}</p>
      <p class="text-xs text-slate-500">
        {{ STATES[permit.etat] ?? permit.etat }} le {{ formatDate(permit.date_autorisation) }} ·
        <template v-if="permit.nb_niveaux">{{ formatInteger(permit.nb_niveaux) }} niveau(x) · </template>
        à {{ formatDistance(permit.distance_m) }}
        <span v-if="permit.precision_geocodage === 'voie'">(position approximative)</span>
      </p>
    </li>
  </ul>
</template>
