<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { formatEuros, formatPercent } from '../../lib/format'
import { estimatePropertyTax, MAX_RENTAL_VALUE } from '../../lib/tax'
import type { TaxeFonciereData } from '../../types/audit'
import StatTile from '../StatTile.vue'

const props = defineProps<{ data: TaxeFonciereData }>()
const emit = defineEmits<{
  /** Taxe foncière annuelle estimée (hors ordures ménagères), ou null si la saisie est vide. */
  estimate: [amount: number | null]
}>()

const rentalValue = ref<number | null>(null)

// Un champ numérique vidé renvoie une chaîne vide : on la ramène à « pas de valeur ».
const enteredValue = computed(() => (typeof rentalValue.value === 'number' ? rentalValue.value : null))
const estimate = computed(() =>
  estimatePropertyTax(enteredValue.value, props.data.taux_tfb_total, props.data.taux_teom),
)
const outOfRange = computed(() => enteredValue.value !== null && estimate.value === null)

watch(estimate, (value) => emit('estimate', value ? Math.round(value.propertyTax) : null))
</script>

<template>
  <StatTile
    label="Taux global sur le bâti"
    :value="formatPercent(data.taux_tfb_total, 2)"
    :hint="`${data.libelle_commune}, ${data.annee}`"
  />
  <dl class="mt-3 space-y-1 text-sm">
    <div class="flex justify-between">
      <dt class="text-slate-500">Part communale</dt>
      <dd class="tabular-nums">{{ formatPercent(data.taux_tfb_commune, 2) }}</dd>
    </div>
    <div class="flex justify-between">
      <dt class="text-slate-500">Part intercommunale</dt>
      <dd class="tabular-nums">{{ formatPercent(data.taux_tfb_epci, 2) }}</dd>
    </div>
    <div class="flex justify-between">
      <dt class="text-slate-500">Ordures ménagères (TEOM)</dt>
      <dd class="tabular-nums">{{ formatPercent(data.taux_teom, 2) }}</dd>
    </div>
  </dl>

  <form class="mt-4 border-t border-slate-100 pt-4" @submit.prevent>
    <label for="rental-value" class="text-xs font-medium text-slate-700">
      Valeur locative cadastrale (€)
    </label>
    <input
      id="rental-value"
      v-model.number="rentalValue"
      type="number"
      inputmode="decimal"
      min="1"
      :max="MAX_RENTAL_VALUE"
      step="1"
      placeholder="ex. 3 200"
      aria-describedby="rental-value-help"
      class="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 tabular-nums focus:border-brand-600 focus:outline-none focus:ring-4 focus:ring-brand-100"
    />
    <p id="rental-value-help" class="mt-1 text-xs text-slate-500">
      Elle figure sur l’avis de taxe foncière du vendeur. Ces taux ne s’appliquent pas au prix du
      bien, mais à la moitié de cette valeur.
    </p>

    <output v-if="estimate" class="mt-3 block rounded-xl bg-brand-50 px-3 py-2" aria-live="polite">
      <span class="block text-xs text-brand-900/80">Taxe foncière estimée</span>
      <span class="block text-2xl font-semibold tracking-tight text-brand-900 tabular-nums">
        {{ formatEuros(estimate.propertyTax) }}<span class="text-sm font-normal"> par an</span>
      </span>
      <span class="mt-1 block text-xs text-brand-900/80">
        Base imposable {{ formatEuros(estimate.taxableBase) }}
        <template v-if="estimate.wasteTax !== null">
          · ordures ménagères {{ formatEuros(estimate.wasteTax) }} · total {{ formatEuros(estimate.total) }}
        </template>
      </span>
      <span class="mt-1 block text-xs text-brand-900/70">
        Hors frais de gestion ajoutés par l’administration (quelques pour cent).
      </span>
    </output>
    <p v-else-if="outOfRange" class="mt-2 text-xs text-rose-700" role="alert">
      Saisissez la valeur locative cadastrale annuelle, pas le prix du bien.
    </p>
  </form>
</template>
