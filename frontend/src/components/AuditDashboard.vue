<script setup lang="ts">
import { computed, ref } from 'vue'

import { SOURCE_INFO } from '../lib/sources'
import type { SourceDataMap, SourceName, SourceResult, SourceResults } from '../types/audit'
import AirCard from './cards/AirCard.vue'
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

const rentPerM2 = computed(() => props.sources.loyers?.data?.loyer_m2_charges_comprises ?? null)
const pricePerM2 = computed(() => props.sources.dvf?.data?.prix_m2_median ?? null)
// Surface et charges partagées entre le bloc copropriété et le simulateur de rendement.
const surfaceM2 = ref(DEFAULT_SURFACE_M2)
const condoCharges = ref<number | null>(null)
const propertyTaxRate = computed(() => props.sources.taxe_fonciere?.data?.taux_tfb_total ?? null)
// Montant calculé par le simulateur de taxe foncière, repris par le calcul de rendement.
const estimatedPropertyTax = ref<number | null>(null)
const yieldPending = computed(() => !resultOf('loyers') || !resultOf('dvf'))
</script>

<template>
  <div class="space-y-10">
    <section aria-labelledby="section-market">
      <h2 id="section-market" class="mb-4 text-lg font-semibold text-slate-900">Marché immobilier</h2>
      <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <SourceCard class="lg:col-span-3" v-bind="SOURCE_INFO.dvf" :result="resultOf('dvf')">
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
        <SourceCard v-bind="SOURCE_INFO.loyers" :result="resultOf('loyers')">
          <template #default="{ data }"><RentCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-bind="SOURCE_INFO.taxe_fonciere" :result="resultOf('taxe_fonciere')">
          <template #default="{ data }">
            <PropertyTaxCard :data="data" @estimate="estimatedPropertyTax = $event" />
          </template>
        </SourceCard>
        <SourceCard v-bind="SOURCE_INFO.copropriete" :result="resultOf('copropriete')">
          <template #default="{ data }">
            <CondoCard :data="data" :surface-m2="surfaceM2" @charges="condoCharges = $event" />
          </template>
        </SourceCard>
        <YieldCard
          v-model:surface="surfaceM2"
          class="lg:col-span-3"
          :loading="yieldPending"
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
        <SourceCard class="lg:col-span-2" v-bind="SOURCE_INFO.georisques" :result="resultOf('georisques')">
          <template #default="{ data }"><RisksCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-bind="SOURCE_INFO.permis_construire" :result="resultOf('permis_construire')">
          <template #default="{ data }"><PermitsCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-bind="SOURCE_INFO.cadastre" :result="resultOf('cadastre')">
          <template #default="{ data }"><ParcelCard :data="data" /></template>
        </SourceCard>
        <SourceCard class="lg:col-span-2" v-bind="SOURCE_INFO.urbanisme" :result="resultOf('urbanisme')">
          <template #default="{ data }"><ZoningCard :data="data" /></template>
        </SourceCard>
      </div>
    </section>

    <section aria-labelledby="section-environment">
      <h2 id="section-environment" class="mb-4 text-lg font-semibold text-slate-900">Énergie et environnement</h2>
      <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <SourceCard v-bind="SOURCE_INFO.dpe" :result="resultOf('dpe')">
          <template #default="{ data }"><EnergyCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-bind="SOURCE_INFO.ensoleillement" :result="resultOf('ensoleillement')">
          <template #default="{ data }"><SunlightCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-bind="SOURCE_INFO.qualite_air" :result="resultOf('qualite_air')">
          <template #default="{ data }"><AirCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-bind="SOURCE_INFO.bruit" :result="resultOf('bruit')">
          <template #default="{ data }"><NoiseCard :data="data" /></template>
        </SourceCard>
      </div>
    </section>

    <section aria-labelledby="section-neighbourhood">
      <h2 id="section-neighbourhood" class="mb-4 text-lg font-semibold text-slate-900">Vie de quartier</h2>
      <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <SourceCard v-bind="SOURCE_INFO.proximite" :result="resultOf('proximite')">
          <template #default="{ data }"><NearbyCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-bind="SOURCE_INFO.ecoles" :result="resultOf('ecoles')">
          <template #default="{ data }"><SchoolsCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-bind="SOURCE_INFO.delinquance" :result="resultOf('delinquance')">
          <template #default="{ data }"><CrimeCard :data="data" /></template>
        </SourceCard>
        <SourceCard class="lg:col-span-2" v-bind="SOURCE_INFO.marche_locatif" :result="resultOf('marche_locatif')">
          <template #default="{ data }"><RentalMarketCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-bind="SOURCE_INFO.connectivite" :result="resultOf('connectivite')">
          <template #default="{ data }"><ConnectivityCard :data="data" /></template>
        </SourceCard>
        <SourceCard v-bind="SOURCE_INFO.reseau_mobile" :result="resultOf('reseau_mobile')">
          <template #default="{ data }"><MobileNetworkCard :data="data" /></template>
        </SourceCard>
      </div>
    </section>
  </div>
</template>
