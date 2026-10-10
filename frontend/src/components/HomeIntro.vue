<script setup lang="ts">
import { RouterLink } from 'vue-router'

import { UNIT_PRICE } from '../lib/pricing'
import { DATA_SOURCES } from '../lib/sources'

/** Présentation du service sous le champ de recherche de la page d'accueil. */
defineEmits<{ demo: [] }>()

const STEPS = [
  {
    title: 'Saisissez l’adresse',
    text: 'Une adresse précise, ou une rue entière si vous hésitez encore sur le numéro.',
  },
  {
    title: 'Lisez l’aperçu gratuit',
    text: 'En quelques secondes et sans compte : chiffres de la commune, qualité de l’air, risques recensés.',
  },
  {
    title: 'Débloquez l’audit complet',
    text: `${UNIT_PRICE} par adresse : tout ce qui est propre au bien, la synthèse et l’export PDF pour votre visite.`,
  },
] as const

const CONTENTS = [
  {
    title: 'Marché immobilier',
    items: ['Ventes réelles des biens voisins', 'Loyers et rendement par type de bien', 'Taxe foncière et charges'],
  },
  {
    title: 'Risques et urbanisme',
    items: ['Inondation, argiles, radon, sites pollués', 'Zonage du plan d’urbanisme et servitudes', 'Permis de construire voisins'],
  },
  {
    title: 'Énergie et environnement',
    items: ['Diagnostics énergétiques du voisinage', 'Bruit des routes et voies ferrées', 'Ensoleillement et qualité de l’air'],
  },
  {
    title: 'Vie de quartier',
    items: ['Écoles, collège de secteur, commerces à pied', 'Revenus du quartier et évolution de la population', 'Fibre, réseau mobile, délinquance'],
  },
] as const
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-14 pb-6">
    <section aria-labelledby="home-steps">
      <h2 id="home-steps" class="text-center text-xl font-semibold tracking-tight text-slate-900">
        Comment ça marche
      </h2>
      <ol class="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <li
          v-for="(step, index) in STEPS"
          :key="step.title"
          class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
        >
          <span
            class="flex size-8 items-center justify-center rounded-full bg-brand-700 text-sm font-semibold text-white"
            aria-hidden="true"
          >
            {{ index + 1 }}
          </span>
          <h3 class="mt-3 font-semibold text-slate-900">{{ step.title }}</h3>
          <p class="mt-1 text-sm text-slate-600">{{ step.text }}</p>
        </li>
      </ol>
    </section>

    <section aria-labelledby="home-contents">
      <h2 id="home-contents" class="text-center text-xl font-semibold tracking-tight text-slate-900">
        Ce que contient l’audit complet
      </h2>
      <ul class="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <li
          v-for="block in CONTENTS"
          :key="block.title"
          class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
        >
          <h3 class="font-semibold text-slate-900">{{ block.title }}</h3>
          <ul class="mt-2 space-y-1.5 text-sm text-slate-700">
            <li v-for="item in block.items" :key="item" class="flex gap-2">
              <svg viewBox="0 0 16 16" class="mt-0.5 size-4 shrink-0 text-brand-600" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path d="M3 8.5 6.5 12 13 4.5" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
              {{ item }}
            </li>
          </ul>
        </li>
      </ul>
      <p class="mt-6 flex flex-wrap items-center justify-center gap-3 text-sm">
        <button
          type="button"
          class="rounded-lg bg-brand-700 px-4 py-2 font-medium text-white hover:bg-brand-900"
          @click="$emit('demo')"
        >
          Voir un rapport d’exemple
        </button>
        <RouterLink
          :to="{ name: 'pricing' }"
          class="rounded-lg border border-slate-300 bg-white px-4 py-2 font-medium text-slate-800 hover:bg-slate-50"
        >
          Voir les tarifs
        </RouterLink>
      </p>
    </section>

    <section aria-labelledby="home-sources" class="rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-sm">
      <h2 id="home-sources" class="text-xl font-semibold tracking-tight text-slate-900">
        Uniquement des données publiques officielles
      </h2>
      <p class="mx-auto mt-2 max-w-3xl text-sm text-slate-600">
        Chaque chiffre vient d’une source ouverte et citée dans le rapport : {{ DATA_SOURCES }}.
        Aucune estimation maison, aucune annonce : ce que l’État et les collectivités publient sur cette adresse,
        réuni et expliqué.
      </p>
    </section>
  </div>
</template>
