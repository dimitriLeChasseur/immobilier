<script setup lang="ts" generic="T">
import { computed } from 'vue'

import { FAILURE_LABELS, isFailure } from '../lib/sources'
import { isLocked, type GhostKind } from '../lib/teaser'
import type { SourceResult } from '../types/audit'
import LockedTeaser from './LockedTeaser.vue'

const props = defineProps<{
  title: string
  emptyText: string
  /** Absent tant que la source n'a pas répondu. */
  result?: SourceResult<T>
  /** Phrase d'accroche affichée quand le serveur a masqué les données de cette source. */
  hook?: string
  /** Carte étroite. */
  compact?: boolean
  /** Carte phare : verrouillée, elle garde l'aperçu flouté et le bouton complet. */
  featured?: boolean
  /** Carte verrouillée : ce qu'elle contient, et la forme de sa silhouette. */
  promise?: string
  ghost?: GhostKind
  /** Retard d'apparition du contenu, en millisecondes (cascade d'un rapport en cache). */
  enterDelay?: number
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
    class="flex min-w-0 flex-col rounded-2xl border border-slate-200/80 bg-white p-5 shadow-[0_1px_2px_rgb(15_23_42/0.04),0_8px_24px_-14px_rgb(15_118_110/0.18)] transition-shadow duration-300 hover:shadow-[0_2px_4px_rgb(15_23_42/0.05),0_16px_40px_-18px_rgb(15_118_110/0.3)]"
    :aria-busy="!result"
  >
    <header class="mb-4 flex items-start justify-between gap-3">
      <h3 class="text-sm font-semibold text-slate-900">{{ title }}</h3>
      <span
        v-if="failureLabel"
        class="shrink-0 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700"
        :title="result?.error ?? undefined"
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

    <!-- Le contenu remplace le squelette en fondu, en glissant de quelques pixels. -->
    <div
      v-else
      class="flex min-w-0 flex-1 flex-col transition-[opacity,translate] duration-500 ease-out starting:translate-y-2 starting:opacity-0 motion-reduce:transition-none"
      :style="enterDelay ? { transitionDelay: `${enterDelay}ms` } : undefined"
    >
      <LockedTeaser
        v-if="locked"
        :hook="hook ?? 'Analyse réalisée pour cette adresse'"
        :featured="featured"
        :promise="promise"
        :ghost="ghost"
      />

      <slot v-else-if="hasData" :data="result.data as T" />

      <p v-else-if="result.status === 'empty'" class="rounded-xl bg-slate-100 px-3 py-2 text-sm text-slate-600">
        {{ emptyText }}
      </p>

      <!-- Panne d'un service public tiers, pas du rapport : dit sans alarme, la cause en infobulle. -->
      <p v-else class="rounded-xl bg-slate-100 px-3 py-2 text-sm text-slate-600">
        Le service public qui fournit cette donnée ne répond pas pour le moment. Le reste du rapport
        n’est pas affecté ; rechargez-le plus tard pour compléter cette carte.
      </p>
    </div>
  </section>
</template>
