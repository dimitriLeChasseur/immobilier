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
</template>
