<script setup lang="ts">
import { inject } from 'vue'

import { UNLOCK_KEY } from '../lib/unlock'

defineProps<{
  /** Version réduite pour les petites cartes : même action, libellé court. */
  compact?: boolean
}>()

const unlock = inject(UNLOCK_KEY, null)
const label = unlock?.label.value ?? 'Créer un compte pour débloquer l’audit complet de cette adresse'
</script>

<template>
  <div class="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 rounded-xl bg-white/40 p-3 text-center">
    <span class="flex size-10 items-center justify-center rounded-full bg-slate-900 text-white shadow" aria-hidden="true">
      <svg viewBox="0 0 20 20" class="size-5" fill="currentColor">
        <path
          fill-rule="evenodd"
          d="M10 1.5A4.5 4.5 0 0 0 5.5 6v2H5a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6a2 2 0 0 0-2-2h-.5V6A4.5 4.5 0 0 0 10 1.5ZM12.5 8V6a2.5 2.5 0 0 0-5 0v2h5Z"
          clip-rule="evenodd"
        />
      </svg>
    </span>
    <button
      type="button"
      class="rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white shadow hover:bg-brand-900"
      :aria-label="unlock?.label.value ?? label"
      @click="unlock?.open()"
    >
      {{ compact ? 'Débloquer' : (unlock?.label.value ?? label) }}
    </button>
  </div>
</template>
