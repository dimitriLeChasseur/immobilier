<script setup lang="ts">
import { computed } from 'vue'

import { formatDecimal, formatInteger } from '../../lib/format'
import type { LoyersData } from '../../types/audit'
import StatTile from '../StatTile.vue'

const props = defineProps<{ data: LoyersData }>()

const TYPOLOGIES = [
  ['t1_t2', 'Appartement de 1 ou 2 pièces'],
  ['t3_plus', 'Appartement de 3 pièces et plus'],
  ['maison', 'Maison'],
] as const

const typologies = computed(() =>
  TYPOLOGIES.flatMap(([id, label]): [string, number][] => {
    const rent = props.data.par_typologie?.[id]?.loyer_m2_charges_comprises
    return typeof rent === 'number' ? [[label, rent]] : []
  }),
)
</script>

<template>
  <StatTile
    label="Loyer d’annonce, appartement"
    :value="`${formatDecimal(data.loyer_m2_charges_comprises)} €/m²`"
    hint="Charges comprises, par mois"
  />
  <p class="mt-3 text-sm text-slate-600">
    Fourchette de {{ formatDecimal(data.intervalle_prediction[0]) }} à
    {{ formatDecimal(data.intervalle_prediction[1]) }} €/m².
  </p>
  <dl v-if="typologies.length" class="mt-3 space-y-1 text-sm">
    <div v-for="[label, rent] in typologies" :key="label" class="flex justify-between">
      <dt class="text-slate-500">{{ label }}</dt>
      <dd class="tabular-nums">{{ formatDecimal(rent) }} €/m²</dd>
    </div>
  </dl>
  <p class="mt-1 text-xs text-slate-500">
    Estimation {{ data.millesime }} à partir de {{ formatInteger(data.nb_observations) }} annonces.
  </p>
</template>
