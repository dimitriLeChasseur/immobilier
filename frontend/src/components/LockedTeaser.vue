<script setup lang="ts">
import { inject } from 'vue'

import { UNLOCK_KEY } from '../lib/unlock'
import LockedOverlay from './LockedOverlay.vue'

defineProps<{
  /** Fait lisible, prouvant que l'analyse a eu lieu. */
  hook: string
  /**
   * Aperçu flouté avec le bouton complet : réservé à la carte phare. Répété sur chaque carte,
   * il noyait le rapport sous le même visuel ; les autres n'affichent qu'une ligne.
   */
  featured?: boolean
}>()

const unlock = inject(UNLOCK_KEY, null)
</script>

<template>
  <p class="mb-3 text-sm font-medium text-slate-700">{{ hook }}</p>
  <div v-if="featured" class="relative min-h-36">
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
    <LockedOverlay />
  </div>
  <div v-else class="locked-row flex items-center gap-2 rounded-xl border border-dashed border-slate-300 bg-slate-50 px-3 py-2">
    <svg viewBox="0 0 20 20" class="size-4 shrink-0 text-slate-500" fill="currentColor" aria-hidden="true">
      <path
        fill-rule="evenodd"
        d="M10 1.5A4.5 4.5 0 0 0 5.5 6v2H5a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6a2 2 0 0 0-2-2h-.5V6A4.5 4.5 0 0 0 10 1.5ZM12.5 8V6a2.5 2.5 0 0 0-5 0v2h5Z"
        clip-rule="evenodd"
      />
    </svg>
    <span class="text-sm text-slate-600">Détail dans l’audit complet</span>
    <button
      type="button"
      class="ml-auto rounded-lg px-2 py-1 text-sm font-medium text-brand-700 underline hover:bg-brand-50"
      :aria-label="unlock?.label.value ?? 'Débloquer l’audit complet de cette adresse'"
      @click="unlock?.open()"
    >
      Débloquer
    </button>
  </div>
</template>
