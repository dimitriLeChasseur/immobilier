<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { formatEuros, formatPercent, grossYield, netYield } from '../../lib/format'
import StatTile from '../StatTile.vue'

const props = defineProps<{
  loading: boolean
  rentPerM2: number | null
  pricePerM2: number | null
  /** Charges annuelles issues du bloc copropriété ; reprises tant que le champ n'est pas modifié. */
  condoChargesEstimate: number | null
  propertyTaxRate: number | null
  /** Montant issu du simulateur de taxe foncière ; repris tant que le champ n'est pas modifié. */
  propertyTaxEstimate?: number | null
}>()

const surface = defineModel<number>('surface', { required: true })
const propertyTax = ref<number | null>(null)
const condoCharges = ref<number | null>(null)
// Tant que l'utilisateur n'a rien saisi ici, les champs suivent les blocs dédiés.
let chargesEdited = false
let taxEdited = false

/** Un champ numérique vidé vaut une chaîne vide : on le compte pour zéro. */
function amount(value: number | null): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

const taxKnown = computed(() => typeof propertyTax.value === 'number')
const gross = computed(() => grossYield(props.rentPerM2, props.pricePerM2))
const net = computed(() => {
  if (props.rentPerM2 === null || props.pricePerM2 === null) return null
  return netYield({
    rentPerM2: props.rentPerM2,
    pricePerM2: props.pricePerM2,
    surfaceM2: surface.value,
    propertyTax: amount(propertyTax.value),
    condoCharges: amount(condoCharges.value),
  })
})
const price = computed(() => (props.pricePerM2 === null ? null : props.pricePerM2 * surface.value))
const yearlyRent = computed(() => (props.rentPerM2 === null ? null : props.rentPerM2 * 12 * surface.value))

watch(
  () => props.condoChargesEstimate,
  (value) => {
    if (!chargesEdited) condoCharges.value = value
  },
  { immediate: true },
)

watch(
  () => props.propertyTaxEstimate,
  (amount) => {
    if (!taxEdited && amount !== undefined) propertyTax.value = amount
  },
)

function onTaxInput(): void {
  taxEdited = true
}

function onChargesInput(): void {
  chargesEdited = true
}
</script>

<template>
  <section class="rounded-2xl border border-brand-100 bg-brand-50 p-5">
    <h3 class="mb-4 text-sm font-semibold text-brand-900">Rendement locatif</h3>

    <output v-if="loading && gross === null" class="block">
      <span class="sr-only">Calcul du rendement</span>
      <span class="skeleton mb-3 block h-8 w-2/5"></span>
      <span class="skeleton block h-3 w-4/5"></span>
    </output>

    <p v-else-if="gross === null" class="text-sm text-brand-900/70">
      Calcul impossible : il manque le prix de vente ou le loyer de référence.
    </p>

    <div v-else class="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div>
        <StatTile label="Rendement brut" :value="formatPercent(gross)" />
        <p class="mt-2 text-xs text-brand-900/70">
          Loyer d’annonce de la commune × 12, rapporté au prix médian des ventes voisines.
          <strong class="font-semibold">Avant</strong> taxe foncière, charges de copropriété, travaux
          et périodes sans locataire.
        </p>
      </div>

      <form class="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:col-span-2" @submit.prevent>
        <p class="text-xs text-brand-900/80 sm:col-span-3">
          Affinez avec vos chiffres pour estimer le rendement net de charges :
        </p>
        <label class="text-xs font-medium text-brand-900">
          Surface (m²)
          <input
            v-model.number="surface"
            type="number"
            min="9"
            max="1000"
            step="1"
            class="mt-1 w-full rounded-lg border border-brand-100 bg-white px-3 py-2 text-sm text-slate-900 tabular-nums"
          />
        </label>
        <label class="text-xs font-medium text-brand-900">
          Taxe foncière (€/an)
          <input
            v-model.number="propertyTax"
            type="number"
            min="0"
            step="10"
            placeholder="Avis du vendeur"
            class="mt-1 w-full rounded-lg border border-brand-100 bg-white px-3 py-2 text-sm text-slate-900 tabular-nums"
            @input="onTaxInput"
          />
        </label>
        <label class="text-xs font-medium text-brand-900">
          Charges de copropriété (€/an)
          <input
            v-model.number="condoCharges"
            type="number"
            min="0"
            step="10"
            class="mt-1 w-full rounded-lg border border-brand-100 bg-white px-3 py-2 text-sm text-slate-900 tabular-nums"
            @input="onChargesInput"
          />
        </label>

        <div class="rounded-xl bg-white px-4 py-3 sm:col-span-3">
          <div class="flex flex-wrap items-end justify-between gap-x-8 gap-y-2">
            <StatTile
              :label="taxKnown ? 'Rendement net de charges' : 'Rendement net de charges, hors taxe foncière'"
              :value="formatPercent(net)"
            />
            <p class="text-xs text-slate-500">
              Prix estimé {{ formatEuros(price) }} · loyers {{ formatEuros(yearlyRent) }}/an
            </p>
          </div>
          <p v-if="!taxKnown" class="mt-2 text-xs text-amber-700">
            Saisissez la taxe foncière, ou calculez-la dans le bloc « Taxe foncière » ci-dessus : son
            montant ne se déduit pas du taux<template v-if="propertyTaxRate !== null"> ({{ formatPercent(propertyTaxRate, 2) }} ici)</template>,
            qui s’applique à une valeur cadastrale propre à chaque logement.
          </p>
          <p class="mt-2 text-xs text-slate-500">
            La taxe d’ordures ménagères est en général refacturée au locataire ; une partie des
            charges de copropriété aussi. Ce calcul reste donc prudent.
          </p>
        </div>
      </form>
    </div>
  </section>
</template>
