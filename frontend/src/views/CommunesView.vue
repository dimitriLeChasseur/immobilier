<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import { communeLinks, type CommuneLink } from '../api/communes'

// Déjà chargée par la garde de la route.
const communes = communeLinks()

// Regroupées par département, dans l'ordre des codes.
const groups = computed(() => {
  const byDepartement = new Map<string, CommuneLink[]>()
  for (const commune of communes) {
    const group = byDepartement.get(commune.departement_code) ?? []
    group.push(commune)
    byDepartement.set(commune.departement_code, group)
  }
  return [...byDepartement.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([code, items]) => ({ code, items: [...items].sort((a, b) => a.nom.localeCompare(b.nom, 'fr')) }))
})
</script>

<template>
  <section class="py-10 sm:py-14" aria-labelledby="communes-title">
    <h1 id="communes-title" class="text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
      Chiffres clés par commune
    </h1>
    <p class="mt-3 max-w-2xl text-base text-slate-600">
      Taxe foncière, sécurité, écoles et logement des principales communes de France, à partir des données publiques.
    </p>
    <div v-for="group in groups" :key="group.code" class="mt-8">
      <h2 class="text-sm font-semibold text-slate-900">Département {{ group.code }}</h2>
      <ul class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <li v-for="commune in group.items" :key="commune.slug">
          <RouterLink :to="{ name: 'commune', params: { slug: commune.slug } }" class="text-brand-700 hover:underline">
            {{ commune.nom }}
          </RouterLink>
        </li>
      </ul>
    </div>
    <p v-if="!groups.length" class="mt-8 text-sm text-slate-500">
      La liste des communes n’est pas disponible sur cet environnement.
    </p>
  </section>
</template>
