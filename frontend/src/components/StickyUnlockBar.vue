<script setup lang="ts">
import { inject, onBeforeUnmount, ref, watch } from 'vue'

import { UNLOCK_KEY } from '../lib/unlock'

/**
 * Barre de déblocage collée en bas de l'écran pendant la lecture d'un aperçu. Elle n'apparaît
 * qu'une fois le bouton principal sorti de l'écran : jamais deux appels côte à côte.
 */
const props = defineProps<{
  /** Bouton principal du rapport ; la barre se montre quand il n'est plus visible. */
  anchor: HTMLElement | null
  /** Ce que l'audit a trouvé, ou ce qu'il contient tant que la synthèse n'est pas arrivée. */
  summary: string
  /** Libellé court du bouton. */
  label: string
}>()

const unlock = inject(UNLOCK_KEY, null)
const visible = ref(false)
let observer: IntersectionObserver | undefined

watch(
  () => props.anchor,
  (anchor) => {
    observer?.disconnect()
    if (!anchor || typeof IntersectionObserver === 'undefined') return
    observer = new IntersectionObserver(([entry]) => {
      visible.value = entry ? !entry.isIntersecting : false
    })
    observer.observe(anchor)
  },
  { immediate: true },
)

onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <div
    v-if="visible"
    class="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white/85 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] shadow-[0_-8px_24px_-12px_rgb(15_23_42/0.15)] backdrop-blur-md transition-[translate,opacity] duration-300 starting:translate-y-full starting:opacity-0 motion-reduce:transition-none"
    role="region"
    aria-label="Débloquer l’audit complet"
  >
    <div class="mx-auto flex max-w-6xl items-center gap-3 px-4 sm:px-6">
      <p class="min-w-0 flex-1 text-sm text-slate-700">
        <span class="line-clamp-2 sm:line-clamp-1">{{ summary }}</span>
      </p>
      <button
        type="button"
        class="shrink-0 rounded-xl bg-brand-700 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brand-700/25 hover:bg-brand-900"
        @click="unlock?.open()"
      >
        {{ label }}
      </button>
    </div>
  </div>
</template>
