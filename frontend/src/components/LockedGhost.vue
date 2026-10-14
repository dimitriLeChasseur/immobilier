<script setup lang="ts">
import type { GhostKind } from '../lib/teaser'

/** Silhouette factice d'une carte verrouillée : fixe, floutée, sans aucune donnée réelle. */
defineProps<{ kind: GhostKind }>()

// Couleurs de l'étiquette énergie A → G, longueurs croissantes comme sur un DPE.
const SCALE = [
  ['A', 'bg-emerald-600', 'w-3/12'],
  ['B', 'bg-emerald-500', 'w-4/12'],
  ['C', 'bg-lime-500', 'w-5/12'],
  ['D', 'bg-yellow-400', 'w-6/12'],
  ['E', 'bg-amber-500', 'w-7/12'],
  ['F', 'bg-orange-600', 'w-8/12'],
  ['G', 'bg-rose-600', 'w-9/12'],
] as const
const ROWS = ['bg-rose-500', 'bg-amber-500', 'bg-emerald-500'] as const
const ROW_WIDTHS = ['w-4/5', 'w-3/5', 'w-2/3'] as const
</script>

<template>
  <div class="locked-blur select-none" aria-hidden="true">
    <div v-if="kind === 'scale'" class="space-y-1">
      <div v-for="[letter, color, width] in SCALE" :key="letter" class="flex items-center gap-2">
        <span class="h-3 rounded-r" :class="[color, width]"></span>
        <span class="text-[10px] font-semibold text-slate-500">{{ letter }}</span>
      </div>
    </div>
    <div v-else-if="kind === 'meter'">
      <p class="text-2xl font-semibold tracking-tight text-slate-900">00 dB</p>
      <div class="relative mt-3 h-2.5 rounded-full bg-linear-to-r from-emerald-500 via-amber-400 to-rose-600">
        <span class="absolute top-1/2 left-3/5 size-4 -translate-y-1/2 rounded-full border-2 border-white bg-slate-900 shadow"></span>
      </div>
    </div>
    <div v-else-if="kind === 'tiles'" class="grid grid-cols-2 gap-3">
      <div v-for="tile in 2" :key="tile" class="rounded-xl bg-slate-50 p-3">
        <p class="text-xs text-slate-500">Valeur</p>
        <p class="mt-1 text-xl font-semibold text-slate-900">0 000</p>
      </div>
    </div>
    <ul v-else class="space-y-2">
      <li v-for="(color, index) in ROWS" :key="color" class="flex items-center gap-2">
        <span class="size-2.5 shrink-0 rounded-full" :class="color"></span>
        <span class="h-3 rounded bg-slate-300" :class="ROW_WIDTHS[index]"></span>
      </li>
    </ul>
  </div>
</template>
