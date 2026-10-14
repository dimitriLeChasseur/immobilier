<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { easeOut, formatLike, splitNumber } from '../lib/countUp'

const props = defineProps<{
  label: string
  value: string
  hint?: string
  tone?: 'default' | 'good' | 'warn' | 'bad'
  /** Chiffre clé : il défile jusqu'à sa valeur la première fois qu'il entre à l'écran. */
  countUp?: boolean
}>()

const TONES = {
  default: 'text-slate-900',
  good: 'text-emerald-700',
  warn: 'text-amber-700',
  bad: 'text-rose-700',
} as const
const DURATION_MS = 700

const root = ref<HTMLElement | null>(null)
const shown = ref(props.value)
let observer: IntersectionObserver | undefined
let frame = 0

function canAnimate(): boolean {
  if (!props.countUp || typeof IntersectionObserver === 'undefined') return false
  return !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

function run(): void {
  const parts = splitNumber(props.value)
  if (!parts) return
  const started = performance.now()
  const step = (now: number): void => {
    const progress = Math.min(1, (now - started) / DURATION_MS)
    shown.value = progress < 1 ? formatLike(parts, parts.value * easeOut(progress)) : props.value
    if (progress < 1) frame = requestAnimationFrame(step)
  }
  frame = requestAnimationFrame(step)
}

onMounted(() => {
  const parts = splitNumber(props.value)
  if (!parts || !canAnimate() || !root.value) return
  // Le compteur part de zéro, puis démarre quand la tuile devient visible.
  shown.value = formatLike(parts, 0)
  observer = new IntersectionObserver(([entry]) => {
    if (!entry?.isIntersecting) return
    observer?.disconnect()
    run()
  })
  observer.observe(root.value)
})

// Nouvelle valeur (simulateur, autre adresse) : affichée telle quelle, sans rejouer le compteur.
watch(
  () => props.value,
  (value) => {
    cancelAnimationFrame(frame)
    observer?.disconnect()
    shown.value = value
  },
)

onBeforeUnmount(() => {
  cancelAnimationFrame(frame)
  observer?.disconnect()
})
</script>

<template>
  <div ref="root">
    <p class="text-xs text-slate-500">{{ label }}</p>
    <p class="text-2xl font-semibold tracking-tight tabular-nums" :class="TONES[tone ?? 'default']">
      <template v-if="countUp">
        <!-- Les lecteurs d'écran lisent la valeur finale, jamais les étapes du compteur. -->
        <span aria-hidden="true">{{ shown }}</span>
        <span class="sr-only">{{ value }}</span>
      </template>
      <template v-else>{{ value }}</template>
    </p>
    <p v-if="hint" class="mt-0.5 text-xs text-slate-500">{{ hint }}</p>
  </div>
</template>
