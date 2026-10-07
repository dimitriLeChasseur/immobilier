<script setup lang="ts">
import { computed } from 'vue'

import { formatDecimal, formatDistance, formatInteger } from '../../lib/format'
import { SCHOOL_KIND_LABELS } from '../../lib/sources'
import type { EcolesData } from '../../types/audit'
import StatTile from '../StatTile.vue'

const props = defineProps<{ data: EcolesData }>()

const KINDS = [
  ['ecole', 'écoles'],
  ['college', 'collèges'],
  ['lycee', 'lycées'],
] as const

// Un IPS d'école ne se compare pas à celui d'un lycée : une moyenne par niveau, face à la France.
const kinds = computed(() =>
  KINDS.flatMap(([id, label]) => {
    const stats = props.data.par_type?.[id]
    if (!stats) return []
    const reference = stats.moyenne_nationale === null ? '' : ` · France : ${formatDecimal(stats.moyenne_nationale)}`
    return [{ id, label, ips_moyen: stats.ips_moyen, hint: `${stats.nb} établissement${stats.nb > 1 ? 's' : ''}${reference}` }]
  }),
)

const VISIBLE_SCHOOLS = 6
const VISIBLE_HIGHER = 5
</script>

<template>
  <div v-if="kinds.length" class="flex flex-wrap gap-x-8 gap-y-3">
    <StatTile
      v-for="kind in kinds"
      :key="kind.id"
      :label="`IPS moyen, ${kind.label}`"
      :value="formatDecimal(kind.ips_moyen)"
      :hint="kind.hint"
    />
  </div>
  <StatTile
    v-else-if="data.etablissements.length"
    label="Indice de position sociale moyen"
    :value="formatDecimal(data.ips_moyen)"
    :hint="`${data.etablissements.length} établissements les plus proches · moyenne nationale ≈ 100`"
  />
  <p v-if="kinds.length" class="mt-2 text-xs text-slate-500">
    Indice de position sociale des établissements à moins de {{ formatDistance(data.rayon_m) }}, par niveau.
  </p>
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
  <p v-if="!data.etablissements.length && !kinds.length" class="text-sm text-slate-500">
    Aucune école, aucun collège ni lycée dans un rayon de {{ formatDistance(data.rayon_m) }}.
  </p>

  <div v-if="data.superieur" class="mt-4 border-t border-slate-100 pt-4">
    <h4 class="text-xs font-medium tracking-wide text-slate-500 uppercase">
      Enseignement supérieur à moins de {{ formatDistance(data.superieur.rayon_m) }}
    </h4>
    <ul v-if="data.superieur.etablissements.length" class="mt-2 divide-y divide-slate-100 text-sm">
      <li
        v-for="school in data.superieur.etablissements.slice(0, VISIBLE_HIGHER)"
        :key="`${school.nom}-${school.distance_m}`"
        class="flex items-center justify-between gap-4 py-2"
      >
        <div class="min-w-0">
          <p class="truncate font-medium text-slate-900">{{ school.nom }}</p>
          <p class="text-xs text-slate-500">
            {{ [school.type, school.secteur].filter(Boolean).join(' ') || 'Établissement' }}<template v-if="school.effectif">
              · {{ formatInteger(school.effectif) }} étudiants</template>
          </p>
        </div>
        <span class="shrink-0 text-sm tabular-nums text-slate-700">{{ formatDistance(school.distance_m) }}</span>
      </li>
    </ul>
    <p v-else class="mt-2 text-sm text-slate-500">Aucun établissement recensé.</p>
    <p v-if="data.superieur.nb > VISIBLE_HIGHER" class="mt-2 text-xs text-slate-500">
      {{ data.superieur.nb }} établissements ou implantations au total.
    </p>
  </div>
</template>
