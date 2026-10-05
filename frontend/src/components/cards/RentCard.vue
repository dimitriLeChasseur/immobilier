<script setup lang="ts">
import { formatDecimal, formatInteger } from '../../lib/format'
import type { LoyersData } from '../../types/audit'
import StatTile from '../StatTile.vue'

defineProps<{ data: LoyersData }>()
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
  <p class="mt-1 text-xs text-slate-500">
    Estimation {{ data.millesime }} à partir de {{ formatInteger(data.nb_observations) }} annonces.
  </p>
</template>
