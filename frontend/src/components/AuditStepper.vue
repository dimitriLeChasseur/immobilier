<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { buildSteps } from '../lib/steps'
import type { SourceName, SourceResults } from '../types/audit'

const props = defineProps<{
  located: boolean
  sources: SourceResults
  sourceNames: readonly SourceName[]
}>()

// Au-delà de ce délai, on explique l'attente plutôt que de laisser l'utilisateur douter.
const PATIENCE_AFTER_MS = 5000
const TICK_MS = 1000

const elapsedMs = ref(0)
let timer: ReturnType<typeof setInterval> | undefined

const steps = computed(() => buildSteps(props.located, props.sources, props.sourceNames))
const total = computed(() => steps.value.reduce((sum, step) => sum + step.expected, 0))
const received = computed(() => steps.value.reduce((sum, step) => sum + step.received, 0))
const percent = computed(() => (total.value ? Math.round((received.value / total.value) * 100) : 0))
const slow = computed(() => elapsedMs.value >= PATIENCE_AFTER_MS)

onMounted(() => {
  timer = setInterval(() => {
    elapsedMs.value += TICK_MS
  }, TICK_MS)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div>
    <progress
      class="audit-progress"
      aria-label="Progression de l’audit"
      :value="percent"
      max="100"
    ></progress>

    <ol class="mt-3 space-y-1.5" aria-label="Étapes de l’audit">
      <li
        v-for="step in steps"
        :key="step.key"
        class="flex items-center gap-2 text-sm"
        :class="step.state === 'pending' ? 'text-slate-400' : 'text-slate-700'"
        :aria-current="step.state === 'active' ? 'step' : undefined"
      >
        <span
          v-if="step.state === 'done'"
          class="flex size-4 shrink-0 items-center justify-center rounded-full bg-brand-600 text-white"
          aria-hidden="true"
        >
          <svg viewBox="0 0 12 12" class="size-2.5" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M2.5 6.5 5 9l4.5-5.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </span>
        <span
          v-else-if="step.state === 'active'"
          class="size-4 shrink-0 animate-spin rounded-full border-2 border-brand-100 border-t-brand-600"
          aria-hidden="true"
        ></span>
        <span v-else class="size-4 shrink-0 rounded-full border-2 border-slate-200" aria-hidden="true"></span>

        <span class="min-w-0 flex-1">{{ step.state === 'done' ? step.doneLabel : step.activeLabel }}</span>
        <span v-if="step.expected > 1 && step.state !== 'pending'" class="text-xs tabular-nums text-slate-400">
          {{ step.received }}/{{ step.expected }}
        </span>
      </li>
    </ol>

    <p v-if="slow" class="mt-3 text-xs text-slate-500">
      Certaines bases publiques répondent lentement : l’analyse complète peut prendre une dizaine
      de secondes. Les résultats déjà reçus s’affichent ci-dessous.
    </p>
  </div>
</template>
