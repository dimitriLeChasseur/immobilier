<script setup lang="ts">
import { computed } from 'vue'

import { formatDistance, formatInteger } from '../../lib/format'
import type { BatimentData } from '../../types/audit'
import StatTile from '../StatTile.vue'

const props = defineProps<{ data: BatimentData }>()

type Row = [label: string, value: string]

function joined(...parts: (string | null | undefined)[]): string | null {
  const known = parts.filter((part): part is string => Boolean(part))
  return known.length ? known.join(', ') : null
}

// Seules les caractéristiques connues de la base sont listées : pas de ligne « inconnu ».
const rows = computed<Row[]>(() => {
  const { data } = props
  const candidates: [string, string | null][] = [
    ['Usage', data.usage ?? null],
    ['Niveaux', data.nb_niveaux ? `${data.nb_niveaux}${data.hauteur_m ? ` (environ ${data.hauteur_m} m)` : ''}` : null],
    ['Logements dans le bâtiment', data.nb_logements ? formatInteger(data.nb_logements) : null],
    ['Murs', data.materiaux?.murs ?? null],
    ['Toiture', data.materiaux?.toit ?? null],
    ['Chauffage', joined(data.chauffage?.energie, data.chauffage?.installation?.toLowerCase())],
  ]
  return candidates.filter((row): row is Row => row[1] !== null)
})

const labels = computed(() => Object.entries(props.data.dpe?.repartition ?? {}))
const condo = computed(() => props.data.copropriete)
const heritage = computed(() => props.data.monument_historique)
</script>

<template>
  <div class="grid grid-cols-1 gap-6 md:grid-cols-2">
    <div class="min-w-0">
      <div class="flex flex-wrap gap-x-8 gap-y-3">
        <StatTile label="Année de construction" :value="data.annee_construction ? String(data.annee_construction) : '—'" />
        <StatTile
          v-if="data.dpe?.classe"
          label="Étiquette énergie du bâtiment"
          :value="data.dpe.classe"
          :hint="labels.length > 1 ? labels.map(([label, count]) => `${count} ${label}`).join(' · ') : undefined"
        />
      </div>
      <dl class="mt-3 space-y-1 text-sm">
        <div v-for="[label, value] in rows" :key="label" class="flex justify-between gap-4">
          <dt class="text-slate-500">{{ label }}</dt>
          <dd class="text-right">{{ value }}</dd>
        </div>
      </dl>
    </div>

    <div class="min-w-0 space-y-3">
      <div v-if="condo" class="rounded-xl bg-slate-50 px-3 py-2">
        <p class="text-sm font-medium text-slate-900">
          Copropriété de {{ formatInteger(condo.nb_lots) }} lots<template v-if="condo.nb_logements">, dont {{ formatInteger(condo.nb_logements) }} logements</template>
        </p>
        <p class="mt-1 text-xs text-slate-600">
          <template v-if="condo.nb_lots_stationnement">{{ condo.nb_lots_stationnement }} lot(s) de stationnement · </template>
          <template v-if="condo.nb_lots_tertiaires">{{ condo.nb_lots_tertiaires }} lot(s) d’activité · </template>
          Immatriculée au registre national sous le n° {{ condo.immatriculation }}.
        </p>
      </div>
      <p v-else-if="condo === null" class="rounded-xl bg-slate-50 px-3 py-2 text-sm text-slate-700">
        Aucune copropriété immatriculée au registre national pour ce bâtiment.
      </p>

      <p v-if="heritage?.dans_perimetre" class="rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-900">
        <strong class="font-semibold">Abords d’un monument historique</strong>
        <template v-if="heritage.nom"> ({{ heritage.nom }}<template v-if="heritage.distance_m">, à {{ formatDistance(heritage.distance_m) }}</template>)</template>.
        Les travaux visibles de l’extérieur sont soumis à l’avis de l’architecte des Bâtiments de France.
      </p>
    </div>
  </div>
  <p class="mt-3 text-xs text-slate-500">
    {{ data.adresse }} · Source : {{ data.origine }}. Données issues de croisements automatiques : à confirmer
    par les diagnostics et le règlement de copropriété.
  </p>
</template>
