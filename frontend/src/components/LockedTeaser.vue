<script setup lang="ts">
import LockedOverlay from './LockedOverlay.vue'

defineProps<{
  /** Fait lisible, prouvant que l'analyse a eu lieu. */
  hook: string
  compact?: boolean
}>()
</script>

<template>
  <p class="mb-3 text-sm font-medium text-slate-700">{{ hook }}</p>
  <div class="relative min-h-36">
    <!-- Contenu factice : la vraie valeur n'a jamais été envoyée par le serveur. -->
    <div class="locked-blur select-none" aria-hidden="true">
      <p class="text-2xl font-semibold tracking-tight text-slate-900">0 000 €/m²</p>
      <p class="mt-1 text-xs text-slate-500">000 éléments analysés à proximité</p>
      <div class="mt-4 space-y-2">
        <div class="h-3 w-full rounded bg-slate-300"></div>
        <div class="h-3 w-4/5 rounded bg-slate-300"></div>
        <div class="h-3 w-3/5 rounded bg-slate-300"></div>
        <div class="h-3 w-2/3 rounded bg-slate-300"></div>
      </div>
    </div>
    <LockedOverlay :compact="compact" />
  </div>
</template>
