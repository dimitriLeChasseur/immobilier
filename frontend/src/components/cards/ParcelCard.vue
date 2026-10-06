<script setup lang="ts">
import { formatInteger } from '../../lib/format'
import type { CadastreData } from '../../types/audit'
import StatTile from '../StatTile.vue'

defineProps<{ data: CadastreData }>()
</script>

<template>
  <StatTile
    label="Surface de la parcelle"
    :value="`${formatInteger(data.contenance_m2)} m²`"
    :hint="`Section ${data.section ?? '—'}, n° ${data.numero ?? '—'}`"
  />
  <p class="mt-3 font-mono text-xs text-slate-500">{{ data.identifiant }}</p>
  <p v-if="data.origine === 'adresse'" class="mt-2 text-xs text-slate-500">
    Parcelle rattachée à cette adresse dans la Base Adresse Nationale (le point de l’adresse est posé sur la voie).
  </p>
</template>
