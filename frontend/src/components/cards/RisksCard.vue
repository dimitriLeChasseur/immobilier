<script setup lang="ts">
import { computed } from 'vue'

import { formatDistance, formatInteger } from '../../lib/format'
import { riskIndicators, type Tone } from '../../lib/insights'
import type { GeorisquesData } from '../../types/audit'

const props = defineProps<{
  data: GeorisquesData
  /** Une servitude de plan de prévention couvre le point (source : urbanisme). */
  preventionPlan?: boolean
}>()

const TONE_CLASSES: Record<Tone, string> = {
  good: 'bg-emerald-50 text-emerald-800',
  warn: 'bg-amber-50 text-amber-800',
  bad: 'bg-rose-50 text-rose-800',
  neutral: 'bg-slate-100 text-slate-600',
}

const indicators = computed(() => riskIndicators(props.data, props.preventionPlan))
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
    <div v-if="data.plans_prevention?.length">
      <dt class="text-slate-500">Plans de prévention des risques de la commune</dt>
      <dd>
        <span v-for="plan in data.plans_prevention" :key="plan.nom" class="block">
          {{ plan.nom }}<template v-if="plan.en_revision"> (en révision)</template>
        </span>
      </dd>
      <dd class="text-xs text-slate-500">
        Vérifiez sur l’état des risques si l’adresse est en zone réglementée.
      </dd>
    </div>
    <div v-if="data.tri?.length">
      <dt class="text-slate-500">Territoire à risque important d’inondation</dt>
      <dd>{{ data.tri.join(', ') }}</dd>
    </div>
    <div v-if="data.anciens_sites_industriels">
      <dt class="text-slate-500">
        Anciens sites industriels à moins de {{ formatDistance(data.anciens_sites_industriels.rayon_m) }}
      </dt>
      <dd v-if="data.anciens_sites_industriels.plus_proches.length">
        {{ formatInteger(data.anciens_sites_industriels.nb_sites) }} recensés, les plus proches :
        <span v-for="site in data.anciens_sites_industriels.plus_proches" :key="`${site.adresse}-${site.distance_m}`" class="block">
          {{ site.adresse ?? 'Adresse non précisée' }}, à {{ formatDistance(site.distance_m) }}
        </span>
      </dd>
      <dd v-else>Aucun recensé</dd>
    </div>
    <div v-if="data.cavites">
      <dt class="text-slate-500">Cavités souterraines à moins de {{ formatDistance(data.cavites.rayon_m) }}</dt>
      <dd v-if="data.cavites.plus_proche">
        {{ formatInteger(data.cavites.nb_cavites) }} recensée(s), la plus proche à
        {{ formatDistance(data.cavites.plus_proche.distance_m) }}<template v-if="data.cavites.plus_proche.nom">
          ({{ data.cavites.plus_proche.nom }})</template>
      </dd>
      <dd v-else>Aucune recensée</dd>
    </div>
    <div v-if="data.mouvements_terrain?.nb_evenements">
      <dt class="text-slate-500">
        Mouvements de terrain à moins de {{ formatDistance(data.mouvements_terrain.rayon_m) }}
      </dt>
      <dd>{{ formatInteger(data.mouvements_terrain.nb_evenements) }} évènement(s) recensé(s)</dd>
    </div>
    <div v-if="data.catastrophes_naturelles">
      <dt class="text-slate-500">Arrêtés de catastrophe naturelle sur la commune</dt>
      <dd>
        {{ formatInteger(data.catastrophes_naturelles.nb_arretes) }}
        <template v-if="data.catastrophes_naturelles.par_type?.length">
          :
          <span v-for="kind in data.catastrophes_naturelles.par_type" :key="kind.type" class="block">
            {{ kind.type }} : {{ kind.nb_arretes }}<template v-if="kind.dernier"> (dernier en {{ kind.dernier }})</template>
          </span>
        </template>
      </dd>
    </div>
    <div v-if="data.risques?.length">
      <dt class="text-slate-500">Risques recensés sur la commune</dt>
      <dd>{{ data.risques.join(', ') }}</dd>
    </div>
  </dl>
</template>
