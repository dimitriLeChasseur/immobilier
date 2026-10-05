<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { formatDecimal, formatInteger } from '../../lib/format'
import type { CoproprieteData } from '../../types/audit'

const props = defineProps<{
  data: CoproprieteData
  /** Surface du simulateur de rendement, pour convertir la moyenne au m² en montant annuel. */
  surfaceM2: number
}>()
const emit = defineEmits<{
  /** Charges annuelles retenues, en euros ; null si le champ est vidé. */
  charges: [amount: number | null]
}>()

const amount = ref<number | null>(null)
// Tant que l'utilisateur n'a rien saisi, le montant suit la moyenne et la surface.
let edited = false

const estimate = computed(() => Math.round(props.data.charges_m2_an * props.surfaceM2))
const scope = computed(() => (props.data.niveau === 'ville' ? 'de la ville' : 'régionale'))
const isEstimate = computed(() => amount.value === estimate.value)

watch(
  estimate,
  (value) => {
    if (!edited) amount.value = value
  },
  { immediate: true },
)
watch(amount, (value) => emit('charges', typeof value === 'number' ? value : null), { immediate: true })

function onInput(): void {
  edited = true
}

function restoreEstimate(): void {
  edited = false
  amount.value = estimate.value
}
</script>

<template>
  <form @submit.prevent>
    <label for="condo-charges" class="text-xs font-medium text-slate-700">
      Charges de copropriété annuelles (€)
    </label>
    <input
      id="condo-charges"
      v-model.number="amount"
      type="number"
      inputmode="decimal"
      min="0"
      step="10"
      aria-describedby="condo-charges-help"
      class="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-lg font-semibold text-slate-900 tabular-nums focus:border-brand-600 focus:outline-none focus:ring-4 focus:ring-brand-100"
      @input="onInput"
    />
    <p id="condo-charges-help" class="mt-2 text-xs text-amber-700">
      Valeur estimée (Moyenne {{ scope }} {{ data.millesime }} :
      {{ formatDecimal(data.charges_m2_an) }} €/m²). Modifiez avec le montant exact de l’annonce.
    </p>
    <p class="mt-1 text-xs text-slate-500">
      Estimation pour {{ formatInteger(surfaceM2) }} m², {{ data.territoire }}. Ce montant est repris
      dans le calcul du rendement net.
      <button
        v-if="!isEstimate"
        type="button"
        class="font-medium text-brand-700 underline hover:text-brand-900"
        @click="restoreEstimate"
      >
        Revenir à l’estimation
      </button>
    </p>
  </form>
</template>
