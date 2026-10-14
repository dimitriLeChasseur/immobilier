<script setup lang="ts">
/**
 * Place de la synthèse pendant le flux : elle n'arrive qu'avec l'évènement final, en tête de
 * rapport. Réservée dès le départ, à peu près à sa hauteur, elle ne repousse pas les cartes
 * déjà lues quand elle apparaît.
 */
defineProps<{
  /** Aperçu gratuit : constats réduits à leur thème, plus courts que dans l'audit complet. */
  teaser?: boolean
}>()

const COLUMNS = ['Points d’attention', 'Points forts'] as const
const FINDINGS = 3
</script>

<template>
  <section class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm" aria-busy="true">
    <h2 class="text-lg font-semibold text-slate-900">L’essentiel</h2>
    <output class="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
      <span class="sr-only">Sélection des constats les plus marquants…</span>
      <span v-for="column in COLUMNS" :key="column" class="block min-w-0">
        <span class="mb-2 block text-xs font-medium tracking-wide text-slate-500 uppercase">{{ column }}</span>
        <span class="block space-y-2">
          <span
            v-for="index in FINDINGS"
            :key="index"
            class="skeleton block rounded-xl"
            :class="teaser ? 'h-16' : 'h-26'"
          ></span>
        </span>
      </span>
    </output>
    <span class="skeleton mt-4 block" :class="teaser ? 'h-10 w-2/3' : 'h-8 w-full'"></span>
  </section>
</template>
