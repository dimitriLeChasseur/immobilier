<script setup lang="ts">
import { computed } from 'vue'

import { formatDate, formatInteger, formatPercent } from '../../lib/format'
import { tenseZoneNotice } from '../../lib/housingRules'
import type { MarcheLocatifData } from '../../types/audit'
import StatTile from '../StatTile.vue'

const props = defineProps<{ data: MarcheLocatifData }>()

const RENT_CONTROL = {
  oui: { text: 'Loyers encadrés', classes: 'bg-amber-50 text-amber-800' },
  partiel: { text: 'Encadrement possible', classes: 'bg-amber-50 text-amber-800' },
  non: { text: 'Pas d’encadrement des loyers', classes: 'bg-emerald-50 text-emerald-800' },
} as const

const OFFICIAL_SIMULATOR_URL = 'https://www.service-public.fr/simulateur/calcul/zones-tendues'

const rentControl = computed(() => props.data.encadrement_loyers)
const tenseZone = computed(() => tenseZoneNotice(props.data.zone_tendue))
const rentControlDetail = computed(() => {
  const rule = rentControl.value
  if (!rule) return ''
  if (rule.statut === 'oui') {
    return `${rule.territoire} : le loyer ne peut pas dépasser le loyer de référence majoré fixé par arrêté.`
  }
  if (rule.statut === 'partiel') {
    return `${rule.territoire}.`
  }
  return 'Le loyer se fixe librement à la première mise en location.'
})
</script>

<template>
  <div class="grid grid-cols-1 gap-6 sm:grid-cols-2">
    <div v-if="data.occupation">
      <div class="flex flex-wrap gap-x-8 gap-y-3">
        <StatTile label="Locataires" :value="formatPercent(data.occupation.part_locataires_pct)" />
        <StatTile label="Propriétaires occupants" :value="formatPercent(data.occupation.part_proprietaires_pct)" />
      </div>
      <dl class="mt-3 space-y-1 text-sm">
        <div class="flex justify-between">
          <dt class="text-slate-500">dont locataires HLM</dt>
          <dd class="tabular-nums">{{ formatPercent(data.occupation.part_locataires_hlm_pct) }}</dd>
        </div>
        <div class="flex justify-between">
          <dt class="text-slate-500">Logements vacants</dt>
          <dd class="tabular-nums">{{ formatPercent(data.occupation.part_vacants_pct) }}</dd>
        </div>
        <div class="flex justify-between">
          <dt class="text-slate-500">Résidences secondaires</dt>
          <dd class="tabular-nums">{{ formatPercent(data.occupation.part_residences_secondaires_pct) }}</dd>
        </div>
      </dl>
      <p class="mt-3 text-xs text-slate-500">
        Quartier « {{ data.occupation.iris.nom }} », {{ formatInteger(data.occupation.logements) }} logements
        (recensement {{ data.occupation.annee }}). Une forte part de locataires signale une demande
        locative installée ; une vacance élevée, un marché plus lent.
      </p>
    </div>
    <p v-else class="text-sm text-slate-500">Pas de donnée de recensement pour ce quartier.</p>

    <div class="space-y-3">
      <div v-if="rentControl" class="rounded-xl px-3 py-2" :class="RENT_CONTROL[rentControl.statut].classes">
        <p class="text-sm font-medium">{{ RENT_CONTROL[rentControl.statut].text }}</p>
        <p class="mt-1 text-xs opacity-90">{{ rentControlDetail }}</p>
        <a
          v-if="rentControl.statut === 'partiel'"
          :href="OFFICIAL_SIMULATOR_URL"
          target="_blank"
          rel="noopener noreferrer"
          class="mt-2 inline-flex items-center gap-1 rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-900 underline-offset-2 hover:bg-amber-200 hover:underline"
        >
          <svg viewBox="0 0 16 16" class="size-3.5 shrink-0" fill="currentColor" aria-hidden="true">
            <path d="M8 1.5a.9.9 0 0 1 .8.45l6 10.5A.9.9 0 0 1 14 13.8H2a.9.9 0 0 1-.8-1.35l6-10.5A.9.9 0 0 1 8 1.5Zm0 4a.7.7 0 0 0-.7.7v3a.7.7 0 0 0 1.4 0v-3A.7.7 0 0 0 8 5.5Zm0 6.6a.8.8 0 1 0 0-1.6.8.8 0 0 0 0 1.6Z" />
          </svg>
          Application partielle selon les communes. Vérifier sur le simulateur officiel du Service Public
          <span class="sr-only">(nouvel onglet)</span>
        </a>
        <p class="mt-1 text-xs opacity-70">Liste officielle vérifiée le {{ formatDate(rentControl.verifie_le) }}.</p>
      </div>
      <div v-if="tenseZone" class="rounded-xl bg-slate-100 px-3 py-2 text-slate-700">
        <p class="text-sm font-medium">{{ tenseZone.title }}</p>
        <p class="mt-1 text-xs">{{ tenseZone.detail }}</p>
        <p class="mt-1 text-xs opacity-70">
          Zonage de la taxe sur les logements vacants ({{ data.zone_tendue?.reference }}) ·
          <a :href="OFFICIAL_SIMULATOR_URL" target="_blank" rel="noopener noreferrer" class="underline">
            simulateur officiel<span class="sr-only"> (nouvel onglet)</span>
          </a>
        </p>
      </div>
      <div v-if="data.zonage_abc" class="rounded-xl bg-slate-100 px-3 py-2 text-slate-700">
        <p class="text-sm font-medium">
          Zone {{ data.zonage_abc.zone }} : marché {{ data.zonage_abc.tendu ? 'tendu' : 'détendu' }}
        </p>
        <p class="mt-1 text-xs">
          Zonage ABC de la commune, qui mesure le déséquilibre entre offre et demande de logements et
          conditionne plusieurs aides et plafonds (prêt à taux zéro, logement intermédiaire).
        </p>
      </div>
      <div class="rounded-xl bg-slate-100 px-3 py-2 text-slate-700">
        <p class="text-sm font-medium">Permis de louer : à vérifier en mairie</p>
        <p class="mt-1 text-xs">
          Aucun recensement national n’existe. Certaines communes imposent une autorisation ou une
          déclaration avant toute mise en location.
        </p>
      </div>
    </div>
  </div>
</template>
