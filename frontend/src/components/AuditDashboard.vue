<script setup lang="ts">
import { computed, ref } from 'vue'

import { SOURCE_INFO } from '../lib/sources'
import { flatPrice } from '../lib/format'
import { inPreventionPlan } from '../lib/insights'
import { isLocked, teaserHook } from '../lib/teaser'
import type { SourceDataMap, SourceName, SourceResult, SourceResults } from '../types/audit'
import AirCard from './cards/AirCard.vue'
import BuildingCard from './cards/BuildingCard.vue'
import CondoCard from './cards/CondoCard.vue'
import ConnectivityCard from './cards/ConnectivityCard.vue'
import CrimeCard from './cards/CrimeCard.vue'
import DvfCard from './cards/DvfCard.vue'
import EnergyCard from './cards/EnergyCard.vue'
import MobileNetworkCard from './cards/MobileNetworkCard.vue'
import NearbyCard from './cards/NearbyCard.vue'
import NoiseCard from './cards/NoiseCard.vue'
import ParcelCard from './cards/ParcelCard.vue'
import PermitsCard from './cards/PermitsCard.vue'
import PropertyTaxCard from './cards/PropertyTaxCard.vue'
import RentalMarketCard from './cards/RentalMarketCard.vue'
import RentCard from './cards/RentCard.vue'
import RisksCard from './cards/RisksCard.vue'
import SchoolsCard from './cards/SchoolsCard.vue'
import SunlightCard from './cards/SunlightCard.vue'
import YieldCard from './cards/YieldCard.vue'
import ZoningCard from './cards/ZoningCard.vue'
import SourceCard from './SourceCard.vue'

const props = defineProps<{
  sources: SourceResults
  /** Vrai une fois le flux terminé : une source sans réponse est alors en échec, plus en attente. */
  settled: boolean
  /** Mode « rue » : une voie n'a pas de parcelle, le bloc cadastre est retiré. */
  street?: boolean
}>()

const DEFAULT_SURFACE_M2 = 50

const NEVER_ANSWERED: SourceResult<never> = {
  status: 'unavailable',
  data: null,
  missing: [],
  error: null,
  duration_ms: 0,
}

function resultOf<K extends SourceName>(name: K): SourceResult<SourceDataMap[K]> | undefined {
  return props.sources[name] ?? (props.settled ? NEVER_ANSWERED : undefined)
}

/** Propriétés d'une carte : titre, résultat, et accroche si le serveur a masqué ses données. */
function card<K extends SourceName>(name: K, compact = false) {
  const result = resultOf(name)
  return { ...SOURCE_INFO[name], result, compact, hook: teaserHook(name, result?.data) }
}

// Une valeur masquée par le serveur (chaîne) n'est pas un nombre : le calcul est alors verrouillé.
function numeric(value: unknown): number | null {
  return typeof value === 'number' ? value : null
}

const rentPerM2 = computed(() => numeric(props.sources.loyers?.data?.loyer_m2_charges_comprises))
// Le loyer de référence est celui des appartements : il se rapporte au prix des appartements
// vendus à proximité, et non à une médiane mêlant maisons et appartements.
const pricePerM2 = computed(() => numeric(flatPrice(props.sources.dvf?.data)))
const yieldLocked = computed(() => isLocked(props.sources.loyers?.data) || isLocked(props.sources.dvf?.data))
// Surface et charges partagées entre le bloc copropriété et le simulateur de rendement.
const surfaceM2 = ref(DEFAULT_SURFACE_M2)
const condoCharges = ref<number | null>(null)
const propertyTaxRate = computed(() => numeric(props.sources.taxe_fonciere?.data?.taux_tfb_total))
// Montant calculé par le simulateur de taxe foncière, repris par le calcul de rendement.
const estimatedPropertyTax = ref<number | null>(null)
const preventionPlan = computed(() => inPreventionPlan(props.sources.urbanisme?.data))
const yieldPending = computed(() => !resultOf('loyers') || !resultOf('dvf'))
</script>

<template>
  <div class="space-y-10">
    <section aria-labelledby="section-market">
      <h2 id="section-market" class="mb-4 text-lg font-semibold text-slate-900">Marché immobilier</h2>
      <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <SourceCard class="lg:col-span-3" v-bind="card('dvf')">
          <template #default="{ data }"><DvfCard :data="data" /></template>
          <template #skeleton>
            <span class="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <span class="block">
                <span class="skeleton mb-4 block h-10 w-1/2"></span>
                <span class="skeleton block h-48 w-full"></span>
              </span>
              <span class="block space-y-3">
                <span v-for="line in 6" :key="line" class="skeleton block h-5 w-full"></span>
              </span>
            </span>
          </template>
        </SourceCard>
        <SourceCard v-bind="card('loyers', true)">
          <template #default="{ data }"><RentCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-bind="card('taxe_fonciere', true)">
          <template #default="{ data }">
            <PropertyTaxCard :data="data" @estimate="estimatedPropertyTax = $event" />
          </template>
        </SourceCard>
        <SourceCard v-bind="card('copropriete', true)">
          <template #default="{ data }">
            <CondoCard :data="data" :surface-m2="surfaceM2" @charges="condoCharges = $event" />
          </template>
        </SourceCard>
        <YieldCard
          v-model:surface="surfaceM2"
          class="lg:col-span-3"
          :loading="yieldPending"
          :locked="yieldLocked"
          :rent-per-m2="rentPerM2"
          :price-per-m2="pricePerM2"
          :condo-charges-estimate="condoCharges"
          :property-tax-rate="propertyTaxRate"
          :property-tax-estimate="estimatedPropertyTax"
        />
      </div>
    </section>

    <section aria-labelledby="section-risks">
      <h2 id="section-risks" class="mb-4 text-lg font-semibold text-slate-900">Risques et urbanisme</h2>
      <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <SourceCard class="lg:col-span-2" v-bind="card('georisques')">
          <template #default="{ data }"><RisksCard :data="data" :prevention-plan="preventionPlan" /></template>
        </SourceCard>
        <SourceCard v-bind="card('permis_construire', true)">
          <template #default="{ data }"><PermitsCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-if="!street" class="lg:col-span-3" v-bind="card('batiment')">
          <template #default="{ data }"><BuildingCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-if="!street" v-bind="card('cadastre', true)">
          <template #default="{ data }"><ParcelCard :data="data" /></template>
        </SourceCard>
        <SourceCard class="lg:col-span-2" v-bind="card('urbanisme')">
          <template #default="{ data }"><ZoningCard :data="data" /></template>
        </SourceCard>
      </div>
    </section>

    <section aria-labelledby="section-environment">
      <h2 id="section-environment" class="mb-4 text-lg font-semibold text-slate-900">Énergie et environnement</h2>
      <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <SourceCard v-bind="card('dpe', true)">
          <template #default="{ data }"><EnergyCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-bind="card('ensoleillement', true)">
          <template #default="{ data }"><SunlightCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-bind="card('qualite_air', true)">
          <template #default="{ data }"><AirCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-bind="card('bruit', true)">
          <template #default="{ data }"><NoiseCard :data="data" /></template>
        </SourceCard>
      </div>
    </section>

    <section aria-labelledby="section-neighbourhood">
      <h2 id="section-neighbourhood" class="mb-4 text-lg font-semibold text-slate-900">Vie de quartier</h2>
      <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <SourceCard v-bind="card('proximite', true)">
          <template #default="{ data }"><NearbyCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-bind="card('ecoles', true)">
          <template #default="{ data }"><SchoolsCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-bind="card('delinquance', true)">
          <template #default="{ data }"><CrimeCard :data="data" /></template>
        </SourceCard>
        <SourceCard class="lg:col-span-2" v-bind="card('marche_locatif')">
          <template #default="{ data }"><RentalMarketCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-bind="card('connectivite', true)">
          <template #default="{ data }"><ConnectivityCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-bind="card('reseau_mobile', true)">
          <template #default="{ data }"><MobileNetworkCard :data="data" /></template>
        </SourceCard>
      </div>
    </section>
  </div>
</template>
