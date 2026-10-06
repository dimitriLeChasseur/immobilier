<script setup lang="ts" generic="T">
import { computed } from 'vue'

import { FAILURE_LABELS, isFailure } from '../lib/sources'
import { isLocked } from '../lib/teaser'
import type { SourceResult } from '../types/audit'
import LockedTeaser from './LockedTeaser.vue'

const props = defineProps<{
  title: string
  emptyText: string
  /** Absent tant que la source n'a pas répondu. */
  result?: SourceResult<T>
  /** Phrase d'accroche affichée quand le serveur a masqué les données de cette source. */
  hook?: string
  /** Carte étroite : bouton de déblocage court. */
  compact?: boolean
}>()

defineSlots<{
  default(props: { data: T }): unknown
  skeleton(): unknown
}>()

const failureLabel = computed(() => (props.result ? FAILURE_LABELS[props.result.status] : undefined))
const hasData = computed(() => props.result?.data != null && !isFailure(props.result.status))
const locked = computed(() => hasData.value && isLocked(props.result?.data))
</script>

<template>
  <section
    class="flex min-w-0 flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
    :aria-busy="!result"
  >
    <header class="mb-4 flex items-start justify-between gap-3">
      <h3 class="text-sm font-semibold text-slate-900">{{ title }}</h3>
      <span
        v-if="failureLabel"
        class="shrink-0 rounded-full bg-rose-50 px-2 py-0.5 text-xs font-medium text-rose-700"
      >
        {{ failureLabel }}
      </span>
      <span
        v-else-if="result?.status === 'partial'"
        class="shrink-0 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700"
        :title="`Sans réponse : ${result.missing.join(', ')}`"
      >
        Partiel
      </span>
    </header>

    <output v-if="!result" class="block">
      <span class="sr-only">Chargement de {{ title }}</span>
      <slot name="skeleton">
        <span class="skeleton mb-3 block h-8 w-2/5"></span>
        <span class="skeleton mb-2 block h-3 w-full"></span>
        <span class="skeleton mb-2 block h-3 w-4/5"></span>
        <span class="skeleton block h-3 w-3/5"></span>
      </slot>
    </output>

    <LockedTeaser v-else-if="locked" :hook="hook ?? 'Analyse réalisée pour cette adresse'" :compact="compact" />

    <slot v-else-if="hasData" :data="result.data as T" />

    <p v-else-if="result.status === 'empty'" class="rounded-xl bg-slate-100 px-3 py-2 text-sm text-slate-600">
      {{ emptyText }}
    </p>

    <p v-else class="text-sm text-slate-500">
      {{ result.error ?? 'Cette source est momentanément indisponible.' }}
    </p>
  </section>
</template>
