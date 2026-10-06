<script setup lang="ts">
import { computed, inject } from 'vue'

import { LOCKED } from '../lib/teaser'
import { UNLOCK_KEY } from '../lib/unlock'
import type { ReportSynthesis } from '../types/audit'

const props = defineProps<{ synthesis: ReportSynthesis }>()

const unlock = inject(UNLOCK_KEY, null)

// En aperçu gratuit, le serveur n'envoie que le thème de chaque constat.
const locked = computed(() =>
  [...props.synthesis.alertes, ...props.synthesis.points_forts].some((item) => item.titre === LOCKED),
)
const columns = computed(() => [
  {
    id: 'alertes',
    title: 'Points d’attention',
    empty: 'Aucune alerte marquante dans les données consultées.',
    items: props.synthesis.alertes,
    tone: 'border-rose-200 bg-rose-50 text-rose-900',
    dot: 'bg-rose-600',
  },
  {
    id: 'points-forts',
    title: 'Points forts',
    empty: 'Aucun point fort marquant dans les données consultées.',
    items: props.synthesis.points_forts,
    tone: 'border-emerald-200 bg-emerald-50 text-emerald-900',
    dot: 'bg-emerald-600',
  },
])
</script>

<template>
  <section aria-labelledby="synthesis-title" class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
    <h2 id="synthesis-title" class="text-lg font-semibold text-slate-900">L’essentiel</h2>
    <div class="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
      <div v-for="column in columns" :key="column.id" class="min-w-0">
        <h3 class="mb-2 text-xs font-medium tracking-wide text-slate-500 uppercase">
          {{ column.title }}<template v-if="locked && column.items.length"> ({{ column.items.length }})</template>
        </h3>
        <p v-if="!column.items.length" class="text-sm text-slate-500">{{ column.empty }}</p>
        <ul v-else class="space-y-2">
          <li
            v-for="(item, index) in column.items"
            :key="`${column.id}-${index}`"
            class="rounded-xl border px-4 py-3"
            :class="column.tone"
          >
            <p class="flex items-center gap-2 text-xs font-medium tracking-wide uppercase opacity-80">
              <span class="size-2 shrink-0 rounded-full" :class="column.dot" aria-hidden="true"></span>
              {{ item.theme }}
            </p>
            <template v-if="item.titre === LOCKED">
              <p class="mt-1 text-sm font-semibold blur-sm select-none" aria-hidden="true">Constat réservé à l’audit</p>
              <p class="sr-only">Constat réservé à l’audit complet.</p>
            </template>
            <template v-else>
              <p class="mt-1 text-sm font-semibold">{{ item.titre }}</p>
              <p class="mt-1 text-sm opacity-90">{{ item.detail }}</p>
            </template>
          </li>
        </ul>
      </div>
    </div>
    <div v-if="locked" class="mt-4 flex flex-wrap items-center justify-between gap-3">
      <p class="text-sm text-slate-600">Le détail de chaque constat est inclus dans l’audit complet.</p>
      <button
        v-if="unlock"
        type="button"
        class="rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-900"
        @click="unlock.open()"
      >
        {{ unlock.label.value }}
      </button>
    </div>
    <p v-else class="mt-4 text-xs text-slate-500">
      Sélection automatique des constats les plus marquants parmi les données publiques consultées. Elle ne
      remplace ni la visite ni les diagnostics obligatoires.
    </p>
  </section>
</template>
